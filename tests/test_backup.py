import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gict.backup import backup_device, backup_directory
from gict.devices import DeviceAdapter, DeviceInfo, DeviceSession
from gict.snapshots import write_report as write_snapshot_report


class TestDeviceSession(DeviceSession):
    def __init__(self, media_root: Path, close_error: Exception | None = None):
        self._media_root = media_root
        self._close_error = close_error
        self.closed = False

    @property
    def media_root(self) -> Path:
        return self._media_root

    def close(self) -> None:
        self.closed = True
        if self._close_error is not None:
            raise self._close_error


class TestDeviceAdapter(DeviceAdapter):
    def __init__(self, session: DeviceSession):
        self._session = session

    def discover(self) -> list[DeviceInfo]:
        return []

    def open(self, device: DeviceInfo) -> DeviceSession:
        return self._session


class BackupWorkflowTests(unittest.TestCase):
    def test_complete_local_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "IMG_1234.JPG").write_bytes(b"photo")
            (source / "clip.MOV").write_bytes(b"video")
            (source / "metadata.dat").write_bytes(b"metadata")

            result = backup_directory(source, root / "backups", "Test Phone")

            snapshot = Path(result["snapshot"])
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["files_found"], 3)
            self.assertEqual(result["files_copied"], 3)
            self.assertTrue((snapshot / "COMPLETE").is_file())
            self.assertFalse((snapshot / "INCOMPLETE").exists())
            self.assertTrue((snapshot / "photos").is_dir())
            self.assertTrue((snapshot / "videos").is_dir())
            self.assertTrue((snapshot / "other").is_dir())

            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "COMPLETE")
            self.assertIn("finished_at", report)

            self.assertEqual((source / "IMG_1234.JPG").read_bytes(), b"photo")
            self.assertEqual((source / "clip.MOV").read_bytes(), b"video")

    def test_rejects_backup_root_inside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()

            with self.assertRaises(ValueError):
                backup_directory(source, source / "backups")

    def test_rejects_device_name_that_escapes_backup_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            backup_root = root / "backups"

            for device_name in ("../escaped", str(root / "absolute")):
                with self.subTest(device_name=device_name):
                    with self.assertRaises(ValueError):
                        backup_directory(source, backup_root, device_name)

            self.assertFalse((root / "escaped").exists())
            self.assertFalse((root / "absolute").exists())

    def test_symlinks_are_reported_without_copying_link_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            outside = root / "outside"
            source.mkdir()
            outside.mkdir()
            outside_file = outside / "external.jpg"
            outside_file.write_bytes(b"external file")
            outside_directory = outside / "linked-directory"
            outside_directory.mkdir()
            (outside_directory / "hidden.jpg").write_bytes(b"hidden file")

            try:
                os.symlink(outside_file, source / "linked-file.jpg")
                os.symlink(
                    outside_directory,
                    source / "linked-directory",
                    target_is_directory=True,
                )
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")

            result = backup_directory(source, root / "backups")

            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["files_found"], 0)
            self.assertEqual(result["files_copied"], 0)
            self.assertTrue(any("symbolic link" in item["error"] for item in result["errors"]))
            snapshot = Path(result["snapshot"])
            self.assertFalse((snapshot / "photos" / "linked-file.jpg").exists())
            self.assertFalse((snapshot / "photos" / "linked-directory" / "hidden.jpg").exists())
            self.assertEqual(outside_file.read_bytes(), b"external file")

    def test_filename_collision_across_subfolders_is_renamed_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            (source / "100APPLE").mkdir(parents=True)
            (source / "101APPLE").mkdir(parents=True)
            (source / "100APPLE" / "IMG_0001.JPG").write_bytes(b"first")
            (source / "101APPLE" / "IMG_0001.JPG").write_bytes(b"second")

            result = backup_directory(source, root / "backups")

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["files_found"], 2)
            self.assertEqual(result["files_copied"], 2)

            snapshot = Path(result["snapshot"])
            copied_files = sorted((snapshot / "photos").rglob("IMG_0001*.JPG"))
            self.assertEqual(len(copied_files), 2)
            self.assertEqual(copied_files[0].name, "IMG_0001.JPG")
            self.assertEqual(copied_files[1].name, "IMG_0001_1.JPG")
            self.assertEqual(copied_files[0].read_bytes(), b"first")
            self.assertEqual(copied_files[1].read_bytes(), b"second")

    def test_empty_source_completes_with_zero_verified_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()

            result = backup_directory(source, root / "backups")

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["files_found"], 0)
            self.assertEqual(result["files_verified"], 0)
            snapshot = Path(result["snapshot"])
            self.assertTrue((snapshot / "COMPLETE").is_file())
            self.assertFalse((snapshot / "INCOMPLETE").exists())

    def test_directory_traversal_error_marks_snapshot_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()

            def fail_walk(path, *, onerror, followlinks):
                onerror(PermissionError("simulated traversal failure"))
                yield str(path), [], []

            with patch("gict.backup.os.walk", side_effect=fail_walk):
                result = backup_directory(source, root / "backups")

            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["files_found"], 0)
            self.assertEqual(result["errors"][0]["stage"], "scan")
            snapshot = Path(result["snapshot"])
            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())

    def test_unexpected_copy_exception_writes_incomplete_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")

            with patch(
                "gict.backup.organized_destination",
                side_effect=RuntimeError("simulated unexpected failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated unexpected"):
                    backup_directory(source, root / "backups")

            snapshot = next((root / "backups" / "Local test source").iterdir())
            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())
            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["errors"][-1]["stage"], "backup")

    def test_complete_report_failure_records_incomplete_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")

            def fail_complete_report(snapshot, report, *, complete):
                if complete:
                    raise OSError("simulated report write failure")
                return write_snapshot_report(snapshot, report, complete=False)

            with patch(
                "gict.backup.write_report",
                side_effect=fail_complete_report,
            ):
                with self.assertRaisesRegex(OSError, "report write failure"):
                    backup_directory(source, root / "backups")

            snapshot = next((root / "backups" / "Local test source").iterdir())
            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())
            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["errors"][-1]["stage"], "backup")

    def test_device_cleanup_failure_downgrades_completed_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")
            session = TestDeviceSession(
                source,
                RuntimeError("simulated unmount failure"),
            )
            device = DeviceInfo("device-id", "Test Phone", "linux")

            result = backup_device(
                TestDeviceAdapter(session),
                device,
                root / "backups",
            )

            self.assertTrue(session.closed)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["errors"][-1]["stage"], "cleanup")
            snapshot = Path(result["snapshot"])
            self.assertTrue((snapshot / "INCOMPLETE").exists())
            self.assertFalse((snapshot / "COMPLETE").exists())
            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["errors"][-1]["stage"], "cleanup")

    def test_device_display_name_is_preserved_but_sanitized_for_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")
            session = TestDeviceSession(source)
            device = DeviceInfo("device-id", "Phone/One", "linux")

            result = backup_device(
                TestDeviceAdapter(session),
                device,
                root / "backups",
            )

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["device_name"], "Phone/One")
            self.assertEqual(
                Path(result["snapshot"]).parent,
                root / "backups" / "Phone_One",
            )

    def test_copy_failure_marks_snapshot_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")

            with patch("gict.backup.copy_verified", side_effect=OSError("simulated failure")):
                result = backup_directory(source, root / "backups", "Test Phone")

            snapshot = Path(result["snapshot"])
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["files_copied"], 0)
            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())
            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertTrue(report["errors"])

    def test_keyboard_interrupt_writes_incomplete_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")

            with patch("gict.backup.copy_verified", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    backup_directory(source, root / "backups", "Test Phone")

            device_root = root / "backups" / "Test Phone"
            snapshots = list(device_root.iterdir())
            self.assertEqual(len(snapshots), 1)
            snapshot = snapshots[0]
            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())

            report = json.loads(
                (snapshot / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertIn("Interrupted by user", report["errors"][-1]["error"])


if __name__ == "__main__":
    unittest.main()
