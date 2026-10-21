import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            unrelated_temporary = destination.with_name(
                destination.name + ".gict-copying"
            )
            unrelated_temporary.write_bytes(b"unrelated file")

            with self.assertRaises(OSError):
                copy_verified(source, destination, retries=1)

            self.assertEqual(destination.read_bytes(), b"preserve this")
            self.assertEqual(unrelated_temporary.read_bytes(), b"unrelated file")
            self.assertEqual(list(root.glob(".gict-copying-*")), [])

    def test_failed_verification_preserves_destination_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"new content")
            destination.write_bytes(b"old verified content")

            def corrupt_temporary(source_path, temporary_path):
                temporary_path.write_bytes(b"corrupted content")

            with patch(
                "gict.integrity.shutil_copystat",
                side_effect=corrupt_temporary,
            ):
                with self.assertRaisesRegex(OSError, "SHA-256 verification failed"):
                    copy_verified(source, destination, retries=1)

            self.assertEqual(destination.read_bytes(), b"old verified content")
            self.assertEqual(list(root.glob(".gict-copying-*")), [])

    def test_interrupted_copy_cleans_temporary_and_preserves_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"new content")
            destination.write_bytes(b"old verified content")

            with patch(
                "gict.integrity.shutil_copystat",
                side_effect=KeyboardInterrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    copy_verified(source, destination, retries=1)

            self.assertEqual(destination.read_bytes(), b"old verified content")
            self.assertEqual(list(root.glob(".gict-copying-*")), [])

    def test_copies_large_unicode_file_and_preserves_modification_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source" / "nested" / "café-文件.bin"
            source.parent.mkdir(parents=True)
            content = bytes(range(256)) * 8192
            source.write_bytes(content)
            timestamp_ns = 1_700_000_000_123_456_789
            os.utime(source, ns=(timestamp_ns, timestamp_ns))
            destination = root / "destination" / source.name

            copy_verified(source, destination)

            self.assertEqual(destination.read_bytes(), content)
            self.assertEqual(
                destination.stat().st_mtime_ns,
                source.stat().st_mtime_ns,
            )


if __name__ == "__main__":
    unittest.main()
