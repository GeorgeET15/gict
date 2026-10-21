"""Portable backup orchestration for GICT."""

import os
import re
import stat
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path, PureWindowsPath

from gict.devices.base import DeviceAdapter, DeviceInfo
from gict.integrity import copy_verified
from gict.organization import organized_destination
from gict.snapshots import create_snapshot, write_report


def list_files(source: Path) -> tuple[list[Path], list[str]]:
    """List regular files and report directory traversal errors."""
    files: list[Path] = []
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(str(exc))

    def inspect_entry(path: Path, *, include_regular_file: bool) -> None:
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            return

        if stat.S_ISLNK(mode):
            errors.append(f"{path}: symbolic links are not supported")
        elif include_regular_file and stat.S_ISREG(mode):
            files.append(path)

    for root, directories, names in os.walk(
        source,
        onerror=onerror,
        followlinks=False,
    ):
        for name in directories:
            inspect_entry(Path(root) / name, include_regular_file=False)
        for name in names:
            inspect_entry(Path(root) / name, include_regular_file=True)

    return sorted(files), errors


def backup_directory(
    source: Path,
    backup_root: Path,
    device_name: str = "Local test source",
    *,
    device_folder_name: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Back up a local directory into a new timestamped snapshot."""
    source = Path(source).resolve()
    backup_root = Path(backup_root).resolve()

    if not source.is_dir():
        raise NotADirectoryError(f"Source directory does not exist: {source}")

    if backup_root == source or source in backup_root.parents:
        raise ValueError("Backup root must not be inside the source directory.")

    folder_name = device_folder_name or device_name
    windows_name = PureWindowsPath(folder_name)
    if (
        folder_name in {"", ".", ".."}
        or Path(folder_name).name != folder_name
        or windows_name.name != folder_name
        or windows_name.drive
        or windows_name.root
    ):
        raise ValueError("Device name must be a single directory name.")

    device_root = backup_root / folder_name
    if not device_root.resolve().is_relative_to(backup_root):
        raise ValueError("Device directory must remain inside the backup root.")

    files, scan_errors = list_files(source)
    if on_progress is not None:
        on_progress({"stage": "scanned", "files_found": len(files)})
    snapshot, started_at = create_snapshot(device_root)

    copied = 0
    used_destinations: set[Path] = set()
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
            if cancel_event is not None and cancel_event.is_set():
                raise KeyboardInterrupt

            destination = organized_destination(src, snapshot)
            destination = _deduplicate_destination(destination, used_destinations)
            used_destinations.add(destination)
            error_message = None
            try:
                copy_verified(src, destination)
                copied += 1
            except OSError as exc:
                error_message = str(exc)
                errors.append({
                    "stage": "copy",
                    "source": str(src.relative_to(source)),
                    "destination": str(destination),
                    "error": error_message,
                })

            if on_progress is not None:
                on_progress({
                    "stage": "copy",
                    "files_found": len(files),
                    "files_copied": copied,
                    "current_file": str(src.relative_to(source)),
                    "error": error_message,
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


def backup_device(
    adapter: DeviceAdapter,
    device: DeviceInfo,
    backup_root: Path,
    *,
    on_progress: Callable[[dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Back up a device session and include cleanup failures in its status."""
    result: dict | None = None

    try:
        with adapter.open(device) as session:
            result = backup_directory(
                session.media_root,
                backup_root,
                device_name=device.name,
                device_folder_name=_safe_device_folder_name(device.name),
                on_progress=on_progress,
                cancel_event=cancel_event,
            )
    except KeyboardInterrupt:
        if result is not None:
            _record_cleanup_failure(
                result,
                "Interrupted while closing the device session.",
            )
        raise
    except Exception as exc:
        if result is None:
            raise
        return _record_cleanup_failure(
            result,
            f"Could not close the device session: {type(exc).__name__}: {exc}",
        )

    return result


def _record_cleanup_failure(result: dict, error: str) -> dict:
    updated = {
        **result,
        "status": "INCOMPLETE",
        "errors": [
            *result["errors"],
            {"stage": "cleanup", "error": error},
        ],
    }
    report_path = write_report(
        Path(result["snapshot"]),
        updated,
        complete=False,
    )
    updated["report_path"] = str(report_path)
    return updated


def _deduplicate_destination(destination: Path, used: set[Path]) -> Path:
    """Append a numeric suffix if this destination is already taken this run."""
    if destination not in used:
        return destination

    suffix = 1
    while True:
        candidate = destination.with_name(
            f"{destination.stem}_{suffix}{destination.suffix}"
        )
        if candidate not in used:
            return candidate
        suffix += 1


def _safe_device_folder_name(device_name: str) -> str:
    folder_name = re.sub(r"[^\w .()\-]", "_", device_name, flags=re.UNICODE)
    folder_name = re.sub(r"\s+", " ", folder_name).strip(" .")
    return folder_name or "iPhone"
