"""Portable snapshot creation and completion reporting."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def unique_snapshot_path(device_root: Path) -> Path:
    """Return a unique timestamped path without creating or overwriting it."""
    device_root = Path(device_root)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
    candidate = device_root / stamp
    suffix = 1

    while candidate.exists():
        candidate = device_root / f"{stamp}_{suffix}"
        suffix += 1

    return candidate


def create_snapshot(device_root: Path) -> tuple[Path, str]:
    """Create a snapshot and immediately mark it incomplete."""
    device_root = Path(device_root)
    device_root.mkdir(parents=True, exist_ok=True)

    snapshot = unique_snapshot_path(device_root)
    snapshot.mkdir(exist_ok=False)

    # If interrupted at any point, the snapshot is visibly incomplete.
    (snapshot / "INCOMPLETE").write_text(
        "INCOMPLETE\n", encoding="utf-8"
    )

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return snapshot, started_at


def write_report(
    snapshot: Path,
    report: dict[str, Any],
    *,
    complete: bool,
) -> Path:
    """Atomically write a report, then update the completion marker."""
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        raise NotADirectoryError(f"Snapshot directory does not exist: {snapshot}")

    status = "COMPLETE" if complete else "INCOMPLETE"
    final_report = dict(report)
    final_report["status"] = status

    report_path = snapshot / "report.json"
    temporary_report = snapshot / "report.json.gict-writing"
    incomplete_marker = snapshot / "INCOMPLETE"
    complete_marker = snapshot / "COMPLETE"

    if not incomplete_marker.exists():
        incomplete_marker.write_text("INCOMPLETE\n", encoding="utf-8")
    complete_marker.unlink(missing_ok=True)

    try:
        with temporary_report.open("w", encoding="utf-8") as stream:
            json.dump(final_report, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()

        temporary_report.replace(report_path)
    finally:
        # A failed report write must not leave a misleading COMPLETE marker.
        if not complete:
            complete_marker.unlink(missing_ok=True)

        temporary_report.unlink(missing_ok=True)

    if complete:
        if incomplete_marker.exists():
            # Rename the marker rather than briefly claiming both statuses.
            incomplete_marker.replace(complete_marker)
        else:
            complete_marker.write_text("COMPLETE\n", encoding="utf-8")
    else:
        incomplete_marker.write_text("INCOMPLETE\n", encoding="utf-8")

    return report_path
