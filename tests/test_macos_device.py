import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gict.devices import DeviceInfo
from gict.devices.macos import MacOSDeviceAdapter


EXECUTABLES = {
    "ifuse": "/tools/ifuse",
    "idevice_id": "/tools/idevice_id",
    "ideviceinfo": "/tools/ideviceinfo",
    "fusermount": "/tools/fusermount",
}


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class MacOSDeviceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.which = lambda name: EXECUTABLES.get(name)

    def test_discovers_devices_as_macos(self):
        def run(command):
            if command[-1] == "--version":
                return completed(command, stdout="ifuse 1.2.1")
            if command[-1] == "-l":
                return completed(command, stdout="mac-device\n")
            return completed(command, stdout="Mac Phone")

        with patch("gict.devices.macos.shutil.which", side_effect=self.which):
            with patch("gict.devices.linux._run", side_effect=run):
                devices = MacOSDeviceAdapter().discover()

        self.assertEqual(
            devices,
            [DeviceInfo("mac-device", "Mac Phone", "macos")],
        )

    def test_requires_documented_fusermount_helper(self):
        def which(name):
            return None if name in {"fusermount", "fusermount3"} else self.which(name)

        with patch("gict.devices.macos.shutil.which", side_effect=which):
            with self.assertRaisesRegex(RuntimeError, "fusermount or fusermount3"):
                MacOSDeviceAdapter().discover()

    def test_mounts_read_only_and_unmounts_its_own_path(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            mounted: set[str] = set()

            def run(command):
                if command[0] == EXECUTABLES["ifuse"]:
                    if command[-1] == "--version":
                        return completed(command, stdout="ifuse 1.2.1")
                    self.assertIn("-o", command)
                    self.assertIn("ro", command)
                    mount_path = Path(command[1])
                    (mount_path / "DCIM").mkdir()
                    mounted.add(str(mount_path))
                    return completed(command)
                if command[0] == EXECUTABLES["fusermount"]:
                    mount_path = Path(command[-1])
                    mounted.remove(str(mount_path))
                    (mount_path / "DCIM").rmdir()
                    return completed(command)
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.macos.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with patch(
                        "gict.devices.macos.os.path.ismount",
                        side_effect=lambda path: str(path) in mounted,
                    ):
                        session = MacOSDeviceAdapter(mount_root).open(
                            DeviceInfo("mac-device", "Mac Phone", "macos")
                        )
                        mount_path = session.media_root.parent
                        with session:
                            self.assertIn(str(mount_path), mounted)

            self.assertEqual(mounted, set())
            self.assertFalse(mount_path.exists())

    def test_existing_mount_is_refused_and_not_unmounted(self):
        with tempfile.TemporaryDirectory() as temp:
            mount_root = Path(temp) / "mnt"
            existing_mount = mount_root / "iphone"
            existing_mount.mkdir(parents=True)
            commands = []

            def run(command):
                commands.append(command)
                if command[-1] == "--version":
                    return completed(command, stdout="ifuse 1.2.1")
                self.fail(f"Unexpected command: {command}")

            with patch("gict.devices.macos.shutil.which", side_effect=self.which):
                with patch("gict.devices.linux._run", side_effect=run):
                    with patch(
                        "gict.devices.macos.os.path.ismount",
                        side_effect=lambda path: Path(path) == existing_mount,
                    ):
                        with self.assertRaisesRegex(RuntimeError, "will not reuse or unmount"):
                            MacOSDeviceAdapter(mount_root).open(
                                DeviceInfo("mac-device", "Mac Phone", "macos")
                            )

            self.assertFalse(any(command[0] == EXECUTABLES["fusermount"] for command in commands))
            self.assertTrue(existing_mount.is_dir())

    def test_rejects_linux_device(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "macOS devices"):
                MacOSDeviceAdapter(Path(temp) / "mnt").open(
                    DeviceInfo("device-id", "Phone", "linux")
                )


if __name__ == "__main__":
    unittest.main()