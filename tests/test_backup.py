import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gict.backup import backup_directory


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
