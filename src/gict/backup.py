"""Portable backup orchestration for GICT."""

import os
from datetime import datetime
from pathlib import Path

from gict.integrity import copy_verified
from gict.organization import organized_destination
from gict.snapshots import create_snapshot, write_report


def list_files(source: Path) -> tuple[list[Path], list[str]]:
    """List regular files and report directory traversal errors."""
    files: list[Path] = []
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(str(exc))

    for root, _, names in os.walk(source, onerror=onerror):
        for name in names:
            path = Path(root) / name
            try:
                if path.is_file():
                    files.append(path)
            except OSError as exc:
                errors.append(f"{path}: {exc}")

    return sorted(files), errors


def backup_directory(
    source: Path,
    backup_root: Path,
    device_name: str = "Local test source",
) -> dict:
    """Back up a local directory into a new timestamped snapshot."""
    source = Path(source).resolve()
    backup_root = Path(backup_root).resolve()

    if not source.is_dir():
        raise NotADirectoryError(f"Source directory does not exist: {source}")

    if backup_root == source or source in backup_root.parents:
        raise ValueError("Backup root must not be inside the source directory.")

    files, scan_errors = list_files(source)
    snapshot, started_at = create_snapshot(backup_root / device_name)

    copied = 0
    errors = [
        {"stage": "scan", "error": error}
        for error in scan_errors
    ]

    report = {
        "tool": "GICT",
        "device_name": device_name,
        "snapshot_started_at": started_at,
        "copy_mode": "SHA-256 verified copy",
        "verification": (
            "SHA-256 of source bytes read during copying compared "
            "with SHA-256 of the temporary destination"
        ),
        "files_found": len(files),
        "files_copied": 0,
        "files_verified": 0,
        "errors": errors,
        "source": str(source),
        "destination": str(snapshot),
        "note": "Source files are read only; GICT does not delete them.",
    }

    def save_report(status_complete: bool) -> dict:
        report["files_copied"] = copied
        report["files_verified"] = copied
        report["finished_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        report_path = write_report(
            snapshot, report, complete=status_complete
        )
        return {
            **report,
            "status": "COMPLETE" if status_complete else "INCOMPLETE",
            "snapshot": str(snapshot),
            "report_path": str(report_path),
        }

    try:
        for src in files:
            destination = organized_destination(src, source, snapshot)
            try:
                copy_verified(src, destination)
                copied += 1
            except OSError as exc:
                errors.append({
                    "stage": "copy",
                    "source": str(src.relative_to(source)),
                    "destination": str(destination),
                    "error": str(exc),
                })

        complete = not errors and copied == len(files)
        return save_report(complete)

    except KeyboardInterrupt:
        errors.append({
            "stage": "backup",
            "error": "Interrupted by user; snapshot is incomplete.",
        })
        save_report(False)
        raise

    except Exception as exc:
        errors.append({
            "stage": "backup",
            "error": f"Unexpected error: {type(exc).__name__}: {exc}",
        })
        save_report(False)
        raise
