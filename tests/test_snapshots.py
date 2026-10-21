import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gict.snapshots import create_snapshot, write_report


class SnapshotTests(unittest.TestCase):
    def test_creates_unique_snapshot_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, _ = create_snapshot(root / "device")
            second, _ = create_snapshot(root / "device")

            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertNotEqual(first, second)

    def test_new_snapshot_starts_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot, _ = create_snapshot(Path(temp) / "device")

            self.assertTrue((snapshot / "INCOMPLETE").is_file())
            self.assertFalse((snapshot / "COMPLETE").exists())

    def test_incomplete_report_has_only_incomplete_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot, _ = create_snapshot(Path(temp) / "device")

            path = write_report(
                snapshot,
                {"files_found": 3, "files_copied": 2},
                complete=False,
            )

            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertTrue((snapshot / "INCOMPLETE").exists())
            self.assertFalse((snapshot / "COMPLETE").exists())

    def test_complete_report_replaces_incomplete_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot, _ = create_snapshot(Path(temp) / "device")

            path = write_report(
                snapshot,
                {"files_found": 2, "files_copied": 2},
                complete=True,
            )

            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "COMPLETE")
            self.assertTrue((snapshot / "COMPLETE").exists())
            self.assertFalse((snapshot / "INCOMPLETE").exists())

    def test_failed_report_write_leaves_only_incomplete_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot, _ = create_snapshot(Path(temp) / "device")
            report_path = write_report(
                snapshot,
                {"files_found": 1, "files_copied": 1},
                complete=True,
            )
            previous_report = report_path.read_bytes()
            original_open = Path.open

            def fail_temporary_report_open(path, *args, **kwargs):
                if path.name == "report.json.gict-writing":
                    raise OSError("simulated report write failure")
                return original_open(path, *args, **kwargs)

            with patch.object(
                Path,
                "open",
                autospec=True,
                side_effect=fail_temporary_report_open,
            ):
                with self.assertRaisesRegex(OSError, "report write failure"):
                    write_report(
                        snapshot,
                        {"files_found": 2, "files_copied": 1},
                        complete=False,
                    )

            self.assertFalse((snapshot / "COMPLETE").exists())
            self.assertTrue((snapshot / "INCOMPLETE").exists())
            self.assertEqual(report_path.read_bytes(), previous_report)
            self.assertFalse((snapshot / "report.json.gict-writing").exists())


if __name__ == "__main__":
    unittest.main()
