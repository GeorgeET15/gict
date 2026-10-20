#!/usr/bin/env python3
"""GICT - George's iPhone Copy Tool

Simple, non-destructive iPhone media copier.
- Copies every regular file under DCIM into a timestamped snapshot.
- Organizes photos and videos by source file date: photos/YYYY/MM and videos/YYYY/MM.
- Keeps other DCIM files under other/ while preserving their relative paths.
- Does not convert, delete, or hash files; copy failures mark the snapshot INCOMPLETE.
- Reuses a working existing iFuse mount and only unmounts mounts created by this run.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def device_name():
    result = run(["ideviceinfo", "-k", "DeviceName"])
    name = result.stdout.strip() if result.returncode == 0 else ""
    if not name:
        raise RuntimeError(
            "Could not read the iPhone name. Unlock the iPhone, trust this computer, "
            "and make sure libimobiledevice can see it. " + (result.stderr.strip() or "")
        )
    safe = re.sub(r"[^\w .()\-]", "_", name, flags=re.UNICODE).strip(" .")
    safe = re.sub(r"\s+", " ", safe) or "iPhone"
    return name, safe


def is_mountpoint(path: Path) -> bool:
    # mountpoint(1) is more reliable for FUSE than relying on os.path.ismount alone.
    if not path.exists():
        return False
    cmd = shutil.which("mountpoint")
    if cmd:
        result = subprocess.run([cmd, "-q", str(path)], capture_output=True)
        return result.returncode == 0
    return os.path.ismount(path)


def mount_has_dcim(path: Path) -> bool:
    try:
        return is_mountpoint(path) and (path / "DCIM").is_dir()
    except OSError:
        return False


def mount_iphone(home: Path, ifuse_bin: Path):
    """Create a fresh mount using the explicitly verified ifuse executable."""
    base = home / "mnt"
    base.mkdir(parents=True, exist_ok=True)

    candidates = [base / "iphone", base / "iphone-gict"]
    candidates += [base / f"iphone-gict-{i}" for i in range(2, 10)]

    # Never silently reuse a mount whose creating ifuse version is unknown.
    for candidate in candidates:
        if mount_has_dcim(candidate):
            raise RuntimeError(
                f"An iPhone is already mounted at {candidate}. "
                "Unmount it cleanly, then run GICT again so it can create "
                "a fresh mount with the verified ifuse executable."
            )

    # Use the first free path; never delete or replace a conflicting file/directory.
    for candidate in candidates:
        if os.path.lexists(candidate):
            continue
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        result = run([str(ifuse_bin), str(candidate)])
        if result.returncode == 0 and mount_has_dcim(candidate):
            print(f"Mounted iPhone at {candidate}.")
            return candidate, True
        detail = (result.stderr or result.stdout or "ifuse did not create a usable DCIM mount").strip()
        # Do not remove the directory or unmount anything on a failed attempt.
        raise RuntimeError(f"Could not mount iPhone at {candidate}: {detail}")

    raise RuntimeError(
        "No usable iPhone mount found and no free mount path is available. "
        "Check existing ifuse mounts before retrying."
    )


def unique_snapshot_path(device_root: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
    candidate = device_root / stamp
    suffix = 1
    while candidate.exists():
        candidate = device_root / f"{stamp}_{suffix}"
        suffix += 1
    return candidate


def list_files(source: Path):
    files = []
    errors = []
    def onerror(exc):
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


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".dng", ".raw"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp", ".mts", ".m2ts"}


def organized_destination(src: Path, source_root: Path, destination_root: Path) -> Path:
    """Use source file modification date for YYYY/MM grouping, without reading media metadata."""
    rel = src.relative_to(source_root)
    ext = src.suffix.lower()
    try:
        date = datetime.fromtimestamp(src.stat().st_mtime)
    except OSError:
        # If timestamp lookup fails, preserve the file rather than skipping it.
        date = datetime.now()
    year_month = Path(f"{date.year:04d}") / f"{date.month:02d}"
    if ext in PHOTO_EXTENSIONS:
        return destination_root / "photos" / year_month / rel
    if ext in VIDEO_EXTENSIONS:
        return destination_root / "videos" / year_month / rel
    return destination_root / "other" / rel


def copy_all(source: Path, destination: Path, files):
    copied = 0
    failed = []
    total = len(files)
    for index, src in enumerate(files, 1):
        rel = src.relative_to(source)
        dest = organized_destination(src, source, destination)
        temp = dest.with_name(dest.name + ".gict-copying")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Retry a failed read once. Each attempt writes to a temporary file so
            # a partial copy is never mistaken for a completed destination.
            last_error = None
            for attempt in range(1, 3):
                try:
                    temp.unlink(missing_ok=True)

                    # Hash the source while copying it, avoiding a second
                    # full read of the iPhone file for source hashing.
                    source_hash = hashlib.sha256()
                    with src.open("rb") as source_file, temp.open("wb") as target_file:
                        while True:
                            chunk = source_file.read(1024 * 1024)
                            if not chunk:
                                break
                            source_hash.update(chunk)
                            target_file.write(chunk)
                        target_file.flush()
                        os.fsync(target_file.fileno())

                    # Preserve source timestamps and other copyable metadata.
                    shutil.copystat(src, temp)

                    # Verify the temporary destination before replacing dest.
                    destination_hash = hashlib.sha256()
                    with temp.open("rb") as copied_file:
                        while True:
                            chunk = copied_file.read(1024 * 1024)
                            if not chunk:
                                break
                            destination_hash.update(chunk)

                    if source_hash.digest() != destination_hash.digest():
                        raise OSError(
                            "SHA-256 verification failed: source and copy differ"
                        )

                    os.replace(temp, dest)
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.5)
            if last_error is not None:
                raise last_error
            copied += 1
        except OSError as exc:
            failed.append({"source": str(rel), "destination": str(dest), "error": str(exc)})
            # Keep any partial temporary copy for recovery/inspection.
        if index == total or index % 10 == 0:
            percent = (index / total * 100) if total else 100
            print(f"Copying: {index}/{total} files ({percent:.1f}%) | copied successfully: {copied}", flush=True)
    return copied, failed


def main():
    print("+-----------------------------------+")
    print("| GICT  - George's iPhone Copy Tool |")
    print("+-----------------------------------+")

    home = Path.home()
    mounted_by_us = False
    mount_path = None
    snapshot = None
    try:
        ifuse_bin = home / ".local/bin/ifuse"
        if not ifuse_bin.is_file() or not os.access(ifuse_bin, os.X_OK):
            raise RuntimeError(
                f"Required executable is missing or not executable: {ifuse_bin}"
            )

        version_result = run([str(ifuse_bin), "--version"])
        version_text = (
            version_result.stdout + "\n" + version_result.stderr
        ).strip()
        if version_result.returncode != 0 or "1.2.1" not in version_text:
            raise RuntimeError(
                f"Expected ifuse 1.2.1 at {ifuse_bin}; got: "
                f"{version_text or 'no version output'}"
            )
        print(f"Using verified executable: {ifuse_bin} ({version_text})")

        for dependency in ("ideviceinfo", "mountpoint"):
            if shutil.which(dependency) is None:
                raise RuntimeError(f"Missing dependency: {dependency}")

        mount_path, mounted_by_us = mount_iphone(home, ifuse_bin)
        name, safe_name = device_name()
        print(f"Connected iPhone: {name}")

        dcim = mount_path / "DCIM"
        if not dcim.is_dir():
            raise RuntimeError(f"DCIM directory is not accessible: {dcim}")

        files, scan_errors = list_files(dcim)
        device_root = home / "GICT_Backups" / safe_name
        snapshot = unique_snapshot_path(device_root)
        snapshot.mkdir(parents=True, exist_ok=False)
        print(f"Backup snapshot: {snapshot}")
        print(f"Source: {dcim}")
        print(f"Photos: {snapshot / 'photos'}/YYYY/MM/")
        print(f"Videos: {snapshot / 'videos'}/YYYY/MM/")
        print(f"Other DCIM files: {snapshot / 'other'}/")
        print(f"Files found: {len(files)}")
        print("Copy mode: SHA-256 verified copy; organized by source modification time; no conversion or deletion.")

        copied, copy_errors = copy_all(dcim, snapshot, files)
        errors = [{"stage": "scan", "error": e} for e in scan_errors]
        errors += [{"stage": "copy", **e} for e in copy_errors]
        status = "COMPLETE" if not errors and copied == len(files) else "INCOMPLETE"
        report = {
            "tool": "GICT",
            "device_name": name,
            "snapshot_started_at": datetime.fromtimestamp(snapshot.stat().st_ctime).astimezone().isoformat(timespec="seconds"),
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": status,
            "copy_mode": "SHA-256 of source bytes during copy, compared with SHA-256 of temporary destination; photos/videos grouped by source modification date YYYY/MM",
            "verification": "SHA-256 source-to-destination comparison before finalizing each file",
            "files_verified": copied,
            "date_basis": "source file modification time exposed by iFuse; EXIF/media creation metadata is not parsed",
            "source": str(dcim),
            "destination": str(snapshot),
            "files_found": len(files),
            "files_copied": copied,
            "errors": errors,
            "note": "Source files on the iPhone were not modified or deleted. Every successfully copied file was SHA-256 verified before being finalized.",
        }
        (snapshot / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        marker = snapshot / status
        marker.write_text(status + "\n", encoding="utf-8")
        other_marker = snapshot / ("INCOMPLETE" if status == "COMPLETE" else "COMPLETE")
        other_marker.unlink(missing_ok=True)

        print(f"\nCopied: {copied}/{len(files)} files")
        print(f"Backup status: {status}")
        print(f"Report: {snapshot / 'report.json'}")
        if errors:
            print(f"Errors: {len(errors)} (see report.json)")
        if status != "COMPLETE":
            return 2
        print("Finished. No files were deleted from the iPhone.")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted. Files already copied have been preserved.")
        if snapshot and snapshot.exists():
            (snapshot / "INCOMPLETE").write_text("Interrupted\n", encoding="utf-8")
        return 130
    except Exception as exc:
        print(f"\nGICT stopped: {exc}", file=sys.stderr)
        if snapshot and snapshot.exists():
            try:
                (snapshot / "INCOMPLETE").write_text(f"Stopped: {exc}\n", encoding="utf-8")
            except OSError:
                pass
        return 1
    finally:
        if mounted_by_us and mount_path is not None and is_mountpoint(mount_path):
            unmount_bin = shutil.which("fusermount3") or shutil.which("fusermount")
            if not unmount_bin:
                print("Warning: no FUSE unmount utility found.", file=sys.stderr)
            else:
                result = run([unmount_bin, "-u", str(mount_path)])
                if result.returncode != 0:
                    print(
                        f"Warning: could not unmount {mount_path}: "
                        f"{result.stderr.strip()}",
                        file=sys.stderr,
                    )


if __name__ == "__main__":
    raise SystemExit(main())
