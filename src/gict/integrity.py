"""Portable file-copy and SHA-256 verification helpers."""

import hashlib
import os
import time
from pathlib import Path
from typing import Iterable


CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def copy_verified(
    source: Path,
    destination: Path,
    *,
    retries: int = 2,
) -> str:
    """
    Copy a file through a temporary destination and verify its SHA-256.

    The destination is replaced only after verification succeeds.
    Returns the verified SHA-256 digest.

    A failed attempt may leave the temporary file for inspection.
    """
    source = Path(source)
    destination = Path(destination)
    temporary = destination.with_name(destination.name + ".gict-copying")

    if retries < 1:
        raise ValueError("retries must be at least 1")

    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = None

    for attempt in range(retries):
        try:
            temporary.unlink(missing_ok=True)

            source_digest = hashlib.sha256()

            with source.open("rb") as source_file, temporary.open("wb") as target:
                while True:
                    chunk = source_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    source_digest.update(chunk)
                    target.write(chunk)

                target.flush()
                os.fsync(target.fileno())

            shutil_copystat(source, temporary)

            destination_digest = hashlib.sha256()
            with temporary.open("rb") as copied:
                while True:
                    chunk = copied.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    destination_digest.update(chunk)

            if source_digest.digest() != destination_digest.digest():
                raise OSError("SHA-256 verification failed: source and copy differ")

            os.replace(temporary, destination)
            return source_digest.hexdigest()

        except OSError as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5)

    assert last_error is not None
    raise last_error


def shutil_copystat(source: Path, destination: Path) -> None:
    """Preserve portable file metadata where supported."""
    import shutil

    shutil.copystat(source, destination)
