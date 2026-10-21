import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gict import __version__
from gict.cli import main
from gict.devices import DeviceInfo


class CliTests(unittest.TestCase):
    def run_cli(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_requires_source_and_backup_root(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--source", stderr.getvalue())
        self.assertIn("--device-id", stderr.getvalue())
        self.assertIn("--list-devices", stderr.getvalue())

    def test_help_option(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--source", stdout.getvalue())
        self.assertIn("--backup-root", stdout.getvalue())

    def test_version_option(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn(f"gict {__version__}", stdout.getvalue())

    def test_rejects_device_name_path_traversal(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main([
                    "--source", "source",
                    "--backup-root", "backups",
                    "--device-name", "../outside",
                ])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("single directory name", stderr.getvalue())

    def test_successful_local_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"test photo")

            exit_code, stdout, stderr = self.run_cli([
                "--source", str(source),
                "--backup-root", str(root / "backups"),
                "--device-name", "Test Phone",
            ])

            self.assertEqual(exit_code, 0)
            self.assertIn("Backup complete: 1 files verified.", stdout)
            self.assertIn("report.json", stdout)
            self.assertEqual(stderr, "")

    def test_invalid_source_returns_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exit_code, stdout, stderr = self.run_cli([
                "--source", str(root / "missing"),
                "--backup-root", str(root / "backups"),
            ])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("Backup failed:", stderr)
            self.assertIn("Source directory does not exist", stderr)

    def test_incomplete_backup_returns_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"test photo")

            with patch(
                "gict.backup.copy_verified",
                side_effect=OSError("simulated copy failure"),
            ):
                exit_code, stdout, stderr = self.run_cli([
                    "--source", str(source),
                    "--backup-root", str(root / "backups"),
                ])

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("Backup incomplete: 1 error(s).", stderr)
            self.assertIn("report.json", stderr)

    def test_lists_devices_without_starting_backup(self):
        devices = [DeviceInfo("id-1", "Phone One", "linux")]
        with patch("sys.platform", "linux"):
            with patch("gict.devices.linux.LinuxDeviceAdapter") as adapter_type:
                adapter_type.return_value.discover.return_value = devices
                exit_code, stdout, stderr = self.run_cli(["--list-devices"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "id-1\tPhone One\n")
        self.assertEqual(stderr, "")
        adapter_type.return_value.open.assert_not_called()

    def test_device_backup_uses_only_explicitly_requested_identifier(self):
        devices = [
            DeviceInfo("id-1", "Phone One", "linux"),
            DeviceInfo("id-2", "Phone Two", "linux"),
        ]
        result = {
            "status": "COMPLETE",
            "files_verified": 4,
            "snapshot": "/temporary/snapshot",
            "report_path": "/temporary/snapshot/report.json",
            "errors": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            with patch("sys.platform", "linux"):
                with patch("gict.devices.linux.LinuxDeviceAdapter") as adapter_type:
                    adapter_type.return_value.discover.return_value = devices
                    with patch("gict.cli.backup_device", return_value=result) as backup:
                        exit_code, stdout, stderr = self.run_cli([
                            "--device-id", "id-2",
                            "--backup-root", temp,
                        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("4 files verified", stdout)
        self.assertEqual(stderr, "")
        backup.assert_called_once_with(
            adapter_type.return_value,
            devices[1],
            Path(temp),
        )

    def test_unknown_device_identifier_fails_without_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("sys.platform", "linux"):
                with patch("gict.devices.linux.LinuxDeviceAdapter") as adapter_type:
                    adapter_type.return_value.discover.return_value = [
                        DeviceInfo("connected-id", "Phone", "linux")
                    ]
                    with patch("gict.cli.backup_device") as backup:
                        exit_code, stdout, stderr = self.run_cli([
                            "--device-id", "other-id",
                            "--backup-root", temp,
                        ])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("No connected iPhone has identifier", stderr)
        backup.assert_not_called()

    def test_device_access_is_rejected_off_linux(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("sys.platform", "win32"):
                exit_code, stdout, stderr = self.run_cli([
                    "--device-id", "id-1",
                    "--backup-root", temp,
                ])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("implemented only for Linux", stderr)


if __name__ == "__main__":
    unittest.main()