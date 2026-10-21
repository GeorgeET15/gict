"""Portable destination organization for iPhone media."""

from datetime import datetime
from pathlib import Path


PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif",
    ".webp", ".tif", ".tiff", ".bmp", ".dng", ".raw",
}

VIDEO_EXTENSIONS = {
    ".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp",
    ".mts", ".m2ts",
}


def organized_destination(
    source_file: Path,
    destination_root: Path,
) -> Path:
    """
    Build a destination path using source modification time.

    Photos: destination_root/photos/YYYY/MM/filename
    Videos: destination_root/videos/YYYY/MM/filename
    Other:  destination_root/other/filename

    The original directory structure is not preserved; only the filename is
    kept, so the caller is responsible for resolving filename collisions
    between files that originated in different source subdirectories.
    """
    source_file = Path(source_file)
    destination_root = Path(destination_root)

    extension = source_file.suffix.lower()

    try:
        modified = datetime.fromtimestamp(source_file.stat().st_mtime)
    except OSError:
        # Preserve the file instead of skipping it if stat fails.
        modified = datetime.now().astimezone()

    year_month = Path(f"{modified.year:04d}") / f"{modified.month:02d}"

    if extension in PHOTO_EXTENSIONS:
        category = "photos"
        grouping = year_month
    elif extension in VIDEO_EXTENSIONS:
        category = "videos"
        grouping = year_month
    else:
        category = "other"
        grouping = Path()

    return destination_root / category / grouping / source_file.name
