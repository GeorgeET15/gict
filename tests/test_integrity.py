import hashlib
import tempfile
import unittest
from pathlib import Path

from gict.integrity import copy_verified, sha256_file


class IntegrityTests(unittest.TestCase):
    def test_copies_and_verifies_various_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_root = root / "source"
            destination_root = root / "destination"
            source_root.mkdir()

            samples = {
                "video.mov": b"video-data\x00" * 10000,
                "photo.jpg": b"photo-data\x01" * 3000,
                "nested/binary.dat": bytes(range(256)) * 100,
                "empty.bin": b"",
            }

            for name, content in samples.items():
                source = source_root / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(content)

                destination = destination_root / name
                result = copy_verified(source, destination)

                expected = hashlib.sha256(content).hexdigest()
                self.assertEqual(result, expected)
                self.assertEqual(sha256_file(destination), expected)
                self.assertEqual(source.read_bytes(), destination.read_bytes())

    def test_existing_destination_survives_missing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "missing.bin"
            destination = root / "destination.bin"
            destination.write_bytes(b"preserve this")

            with self.assertRaises(OSError):
                copy_verified(source, destination, retries=1)

            self.assertEqual(destination.read_bytes(), b"preserve this")


if __name__ == "__main__":
    unittest.main()
