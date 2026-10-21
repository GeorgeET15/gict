import unittest
from pathlib import Path
from unittest.mock import patch

import gict.setup_check as setup_check
from gict.devices.linux import LinuxDeviceAdapter
from gict.setup_check import (
    all_install_commands,
    check_iphone_dependencies,
    detect_distro,
    install_command_for,
    overall_status,
)

ALL_TOOLS = {
    "ifuse": "/usr/bin/ifuse",
    "idevice_id": "/usr/bin/idevice_id",
    "ideviceinfo": "/usr/bin/ideviceinfo",
    "mountpoint": "/usr/bin/mountpoint",
    "fusermount3": "/usr/bin/fusermount3",
    "fusermount": None,
}


def which(tools):
    return lambda name: tools.get(name)


class DependencyCheckTests(unittest.TestCase):
    def test_all_dependencies_present_on_linux_with_correct_ifuse(self):
        with patch("sys.platform", "linux"):
            with patch.object(setup_check.shutil, "which", side_effect=which(ALL_TOOLS)):
                with patch.object(LinuxDeviceAdapter, "_verify_ifuse", return_value=None):
                    checks = check_iphone_dependencies()

        statuses = {check.name: check.status for check in checks}
        self.assertTrue(all(status == "available" for status in statuses.values()))
        self.assertEqual(overall_status(checks), "Ready for iPhone backups")

    def test_missing_each_simple_dependency_is_reported_individually(self):
        for missing in ("idevice_id", "ideviceinfo", "mountpoint"):
            tools = dict(ALL_TOOLS)
            tools[missing] = None
            with self.subTest(missing=missing):
                with patch("sys.platform", "linux"):
                    with patch.object(setup_check.shutil, "which", side_effect=which(tools)):
                        with patch.object(LinuxDeviceAdapter, "_verify_ifuse", return_value=None):
                            checks = check_iphone_dependencies()

                by_name = {check.name: check for check in checks}
                self.assertEqual(by_name[missing].status, "missing")
                self.assertEqual(overall_status(checks), "Setup incomplete")

    def test_incorrect_ifuse_version_is_incompatible_not_missing(self):
        with patch("sys.platform", "linux"):
            with patch.object(setup_check.shutil, "which", side_effect=which(ALL_TOOLS)):
                with patch.object(
                    LinuxDeviceAdapter,
                    "_verify_ifuse",
                    side_effect=RuntimeError(
                        "GICT currently requires ifuse 1.2.1; found ifuse 1.2.2"
                    ),
                ):
                    checks = check_iphone_dependencies()

        by_name = {check.name: check for check in checks}
        self.assertEqual(by_name["ifuse"].status, "incompatible")
        self.assertIn("1.2.1", by_name["ifuse"].detail)
        self.assertEqual(overall_status(checks), "Setup incomplete")

    def test_correct_ifuse_version_is_available(self):
        with patch.object(setup_check.shutil, "which", return_value="/usr/bin/ifuse"):
            with patch.object(LinuxDeviceAdapter, "_verify_ifuse", return_value=None):
                check = setup_check._check_ifuse()

        self.assertEqual(check.status, "available")
        self.assertIn("1.2.1", check.detail)

    def test_missing_ifuse_is_missing_not_incompatible(self):
        with patch.object(setup_check.shutil, "which", return_value=None):
            check = setup_check._check_ifuse()

        self.assertEqual(check.status, "missing")

    def test_unexpected_ifuse_check_error_is_unknown(self):
        with patch.object(setup_check.shutil, "which", return_value="/usr/bin/ifuse"):
            with patch.object(
                LinuxDeviceAdapter, "_verify_ifuse", side_effect=PermissionError("denied")
            ):
                check = setup_check._check_ifuse()

        self.assertEqual(check.status, "unknown")

    def test_fusermount3_only_is_available(self):
        tools = {"fusermount3": "/usr/bin/fusermount3", "fusermount": None}
        with patch.object(setup_check.shutil, "which", side_effect=which(tools)):
            check = setup_check._check_unmount_tool()
        self.assertEqual(check.status, "available")

    def test_fusermount_only_is_available(self):
        tools = {"fusermount3": None, "fusermount": "/usr/bin/fusermount"}
        with patch.object(setup_check.shutil, "which", side_effect=which(tools)):
            check = setup_check._check_unmount_tool()
        self.assertEqual(check.status, "available")

    def test_neither_fusermount_variant_is_missing(self):
        tools = {"fusermount3": None, "fusermount": None}
        with patch.object(setup_check.shutil, "which", side_effect=which(tools)):
            check = setup_check._check_unmount_tool()
        self.assertEqual(check.status, "missing")

    def test_non_linux_platform_is_incompatible(self):
        with patch("sys.platform", "darwin"):
            check = setup_check._check_linux_platform()
        self.assertEqual(check.status, "incompatible")
        self.assertIn("darwin", check.detail)


class DistroDetectionTests(unittest.TestCase):
    def _detect_with(self, content):
        with patch.object(Path, "read_text", return_value=content):
            return detect_distro()

    def test_debian(self):
        self.assertEqual(self._detect_with("ID=debian\nNAME=Debian\n"), "debian")

    def test_ubuntu(self):
        self.assertEqual(self._detect_with('ID=ubuntu\nID_LIKE=debian\nNAME="Ubuntu"\n'), "debian")

    def test_fedora(self):
        self.assertEqual(self._detect_with("ID=fedora\nNAME=Fedora\n"), "fedora")

    def test_arch(self):
        self.assertEqual(self._detect_with('ID=arch\nNAME="Arch Linux"\n'), "arch")

    def test_unrecognized_distro_falls_back_through_id_like(self):
        self.assertEqual(
            self._detect_with('ID=popos\nID_LIKE="ubuntu debian"\nNAME=Pop\n'), "debian"
        )

    def test_completely_unknown_distro(self):
        self.assertEqual(self._detect_with("ID=solus\nNAME=Solus\n"), "unknown")

    def test_malformed_os_release_does_not_raise(self):
        self.assertEqual(self._detect_with("not a key value file\n### comment\n"), "unknown")

    def test_empty_os_release(self):
        self.assertEqual(self._detect_with(""), "unknown")

    def test_missing_os_release_file_does_not_raise(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(detect_distro(), "unknown")

    def test_unreadable_os_release_file_does_not_raise(self):
        with patch.object(Path, "read_text", side_effect=PermissionError):
            self.assertEqual(detect_distro(), "unknown")


class InstallCommandTests(unittest.TestCase):
    def test_known_distros_have_commands(self):
        self.assertIn("apt install", install_command_for("debian"))
        self.assertIn("dnf install", install_command_for("fedora"))
        self.assertIn("pacman -S", install_command_for("arch"))

    def test_unknown_distro_has_no_command(self):
        self.assertIsNone(install_command_for("unknown"))

    def test_all_install_commands_cover_every_known_distro(self):
        commands = all_install_commands()
        self.assertEqual(len(commands), 3)
        for command in commands.values():
            self.assertIn("ifuse", command)


if __name__ == "__main__":
    unittest.main()
