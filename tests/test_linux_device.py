import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gict.devices import DeviceInfo
from gict.devices.linux import LinuxDeviceAdapter


EXECUTABLES = {
    "ifuse": "/tools/ifuse",
    "idevice_id": "/tools/idevice_id",
    "ideviceinfo": "/tools/ideviceinfo",
    "mountpoint": "/tools/mountpoint",
    "fusermount3": "/tools/fusermount3",
}


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class LinuxDeviceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.which = lambda name: EXECUTABLES.get(name)

    def test_discovery_returns_device_ids_and_names(self):
        def run(command):
            if command[-1] == "--version":
                return completed(command, stdout="ifuse 1.2.1")
            if command[-1] == "-l":
                return completed(command, stdout="device-one\ndevice-two\n")
            return completed(command, stdout=f"Phone {command[2][-1]}")

        with patch("gict.devices.linux.shutil.which", side_effect=self.which):
            with patch("gict.devices.linux._run", side_effect=run):
                devices = LinuxDeviceAdapter().discover()

        self.assertEqual(
            devices,
            [
                DeviceInfo("device-one", "Phone e", "linux"),
                DeviceInfo("device-two", "Phone o", "linux"),
            ],
        )

    def test_missing_dependency_is_reported(self):
        def which(name):
            return None if name == "ideviceinfo" else self.which(name)

        with patch("gict.devices.linux.shutil.which", side_effect=which):
            with self.assertRaisesRegex(RuntimeError, "ideviceinfo"):
                LinuxDeviceAdapter().discover()

    def test_wrong_ifuse_version_is_rejected(self):
        with patch("gict.devices.linux.shutil.which", side_effect=self.which):
            with patch(
                "gict.devices.linux._run",
                return_value=completed(["ifuse", "--version"], stdout="ifuse 1.2.2"),
            ):
                with self.assertRaisesRegex(RuntimeError, "requires ifuse 1.2.1"):
                    LinuxDeviceAdapter().discover()

    def test_opens_and_unmounts_only_its_own_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            mounted: set[str] = set()
            commands = []

            def run(command):
                commands.append(command)
                if command[0] == EXECUTABLES["ifuse"]:
                    if command[-1] == "--version":
                        return completed(command, stdout="ifuse 1.2.1")
                    self.assertIn("-o", command)
                    self.assertIn("ro", command)
                    mount_path = Path(command[1])
                    (mount_path / "DCIM").mkdir()
                    mounted.add(str(mount_path))
                    return completed(command)
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(
                        command,
                        returncode=0 if command[-1] in mounted else 1,
                    )
                if command[0] == EXECUTABLES["fusermount3"]:
                    mount_path = Path(command[-1])
                    mounted.remove(str(mount_path))
                    (mount_path / "DCIM").rmdir()
                    return completed(command)
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.linux.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    session = LinuxDeviceAdapter(mount_root).open(
                        DeviceInfo("device-one", "Test Phone", "linux")
                    )
                    mount_path = session.media_root.parent
                    self.assertEqual(session.media_root, mount_path / "DCIM")
                    with session:
                        self.assertIn(str(mount_path), mounted)

            self.assertEqual(mounted, set())
            unmount_commands = [
                command
                for command in commands
                if command[0] == EXECUTABLES["fusermount3"]
            ]
            self.assertEqual(
                unmount_commands,
                [[EXECUTABLES["fusermount3"], "-u", str(mount_path)]],
            )
            self.assertFalse(mount_path.exists())

    def test_existing_mount_is_refused_and_never_unmounted(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            existing_mount = mount_root / "iphone"
            existing_mount.mkdir(parents=True)
            commands = []

            def run(command):
                commands.append(command)
                if command[-1] == "--version":
                    return completed(command, stdout="ifuse 1.2.1")
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(
                        command,
                        returncode=0 if command[-1] == str(existing_mount) else 1,
                    )
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.linux.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with self.assertRaisesRegex(RuntimeError, "will not reuse or unmount"):
                        LinuxDeviceAdapter(mount_root).open(
                            DeviceInfo("device-one", "Test Phone", "linux")
                        )

            self.assertFalse(any(command[0] == EXECUTABLES["ifuse"] and command[-1] != "--version" for command in commands))
            self.assertFalse(any("fusermount" in command[0] for command in commands))
            self.assertTrue(existing_mount.is_dir())

    def test_device_discovery_command_failure_is_reported(self):
        def run(command):
            if command[-1] == "--version":
                return completed(command, stdout="ifuse 1.2.1")
            return completed(command, returncode=1, stderr="usbmuxd unavailable")

        with patch("gict.devices.linux.shutil.which", side_effect=self.which):
            with patch("gict.devices.linux._run", side_effect=run):
                with self.assertRaisesRegex(RuntimeError, "usbmuxd unavailable"):
                    LinuxDeviceAdapter().discover()

    def test_ifuse_mount_failure_does_not_unmount_or_leave_mount_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            commands = []

            def run(command):
                commands.append(command)
                if command[-1] == "--version":
                    return completed(command, stdout="ifuse 1.2.1")
                if command[0] == EXECUTABLES["ifuse"]:
                    return completed(command, returncode=1, stderr="mount denied")
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(command, returncode=1)
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.linux.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with self.assertRaisesRegex(RuntimeError, "mount denied"):
                        LinuxDeviceAdapter(mount_root).open(
                            DeviceInfo("device-one", "Test Phone", "linux")
                        )

            self.assertEqual(list(mount_root.iterdir()), [])
            self.assertFalse(any("fusermount" in command[0] for command in commands))

    def test_interrupted_mount_setup_unmounts_its_new_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            mounted: set[str] = set()

            def run(command):
                if command[0] == EXECUTABLES["ifuse"]:
                    if command[-1] == "--version":
                        return completed(command, stdout="ifuse 1.2.1")
                    mount_path = Path(command[1])
                    (mount_path / "DCIM").mkdir()
                    mounted.add(str(mount_path))
                    raise KeyboardInterrupt
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(
                        command,
                        returncode=0 if command[-1] in mounted else 1,
                    )
                if command[0] == EXECUTABLES["fusermount3"]:
                    mount_path = Path(command[-1])
                    mounted.remove(str(mount_path))
                    (mount_path / "DCIM").rmdir()
                    return completed(command)
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.linux.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with self.assertRaises(KeyboardInterrupt):
                        LinuxDeviceAdapter(mount_root).open(
                            DeviceInfo("device-one", "Test Phone", "linux")
                        )

            self.assertEqual(mounted, set())
            self.assertEqual(list(mount_root.iterdir()), [])

    def test_interrupted_media_root_check_closes_session(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            mounted: set[str] = set()
            original_is_dir = Path.is_dir

            def run(command):
                if command[0] == EXECUTABLES["ifuse"]:
                    if command[-1] == "--version":
                        return completed(command, stdout="ifuse 1.2.1")
                    mount_path = Path(command[1])
                    (mount_path / "DCIM").mkdir()
                    mounted.add(str(mount_path))
                    return completed(command)
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(
                        command,
                        returncode=0 if command[-1] in mounted else 1,
                    )
                if command[0] == EXECUTABLES["fusermount3"]:
                    mount_path = Path(command[-1])
                    mounted.remove(str(mount_path))
                    (mount_path / "DCIM").rmdir()
                    return completed(command)
                self.fail(f"Unexpected command: {command}")

            def is_dir(path):
                if path.name == "DCIM":
                    raise KeyboardInterrupt
                return original_is_dir(path)

            with patch("gict.devices.linux.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with patch.object(Path, "is_dir", autospec=True, side_effect=is_dir):
                        with self.assertRaises(KeyboardInterrupt):
                            LinuxDeviceAdapter(mount_root).open(
                                DeviceInfo("device-one", "Test Phone", "linux")
                            )

            self.assertEqual(mounted, set())
            self.assertEqual(list(mount_root.iterdir()), [])

    def test_unmount_failure_is_reported_and_mount_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_path = Path(temp) / "owned-mount"
            mount_path.mkdir()

            def run(command):
                if command[0] == EXECUTABLES["mountpoint"]:
                    return completed(command, returncode=0)
                if command[0] == EXECUTABLES["fusermount3"]:
                    return completed(command, returncode=1, stderr="busy")
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.linux._run", side_effect=run):
                from gict.devices.linux import LinuxDeviceSession

                session = LinuxDeviceSession(
                    mount_path,
                    "Test Phone",
                    EXECUTABLES["mountpoint"],
                    EXECUTABLES["fusermount3"],
                )
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    session.close()

            self.assertTrue(mount_path.exists())

    def test_rejects_non_linux_device(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = LinuxDeviceAdapter(Path(temp) / "mnt")
            with self.assertRaisesRegex(ValueError, "Linux devices"):
                adapter.open(DeviceInfo("device-one", "Test Phone", "windows"))


if __name__ == "__main__":
    unittest.main()