import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from gict.organization import organized_destination


class OrganizationTests(unittest.TestCase):
    def test_organizes_photos_and_videos_by_modification_date(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_root = root / "DCIM"
            destination_root = root / "snapshot"
            source_root.mkdir()

            cases = [
                ("100APPLE/IMG_1234.HEIC", "photos"),
                ("101APPLE/IMG_1235.MOV", "videos"),
            ]

            for relative, category in cases:
                source = source_root / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b"test")
                timestamp = datetime(2024, 3, 15, 12, 0).timestamp()
                import os
                os.utime(source, (timestamp, timestamp))

                result = organized_destination(
                    source, source_root, destination_root
                )

                self.assertEqual(
                    result,
                    destination_root / category / "2024" / "03" / relative,
                )

    def test_preserves_relative_path_for_other_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_root = root / "DCIM"
            source_root.mkdir()
            source = source_root / "nested" / "metadata.dat"
            source.parent.mkdir()
            source.write_bytes(b"metadata")

            result = organized_destination(
                source, source_root, root / "snapshot"
            )

            self.assertEqual(
                result,
                root / "snapshot" / "other" / "nested" / "metadata.dat",
            )


if __name__ == "__main__":
    unittest.main()
