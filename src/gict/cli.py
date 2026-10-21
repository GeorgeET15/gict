"""Development command-line interface."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath

from gict import __version__
from gict.backup import backup_device, backup_directory


def _device_name_argument(value: str) -> str:
    windows_path = PureWindowsPath(value)
    if (
        value in {"", ".", ".."}
        or Path(value).name != value
        or windows_path.name != value
        or windows_path.drive
        or windows_path.root
    ):
        raise argparse.ArgumentTypeError(
            "device name must be a single directory name"
        )
    return value


def _device_adapter():
    if sys.platform == "linux":
        from gict.devices.linux import LinuxDeviceAdapter

        return LinuxDeviceAdapter()
    raise RuntimeError(
        "iPhone device access is currently implemented only for Linux."
    )


def _print_backup_result(result: dict) -> int:
    if result["status"] != "COMPLETE":
        print(
            f"Backup incomplete: {len(result['errors'])} error(s). "
            f"Snapshot: {result['snapshot']} "
            f"Report: {result['report_path']}",
            file=sys.stderr,
        )
        return 1

    print(f"Backup complete: {result['files_verified']} files verified.")
    print(f"Snapshot: {result['snapshot']}")
    print(f"Report: {result['report_path']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None and len(sys.argv) <= 1:
        from gict.tui import run as run_tui

        return run_tui()

    parser = argparse.ArgumentParser(
        prog="gict",
        description="Copy and verify local files or media from a Linux iPhone.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="local source directory to copy",
    )
    parser.add_argument(
        "--device-id",
        help="explicit connected iPhone identifier to back up (Linux only)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="list connected iPhones without starting a backup (Linux only)",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        help="directory where timestamped snapshots are created",
    )
    parser.add_argument(
        "--device-name",
        type=_device_name_argument,
        help="display name used for a local-source snapshot",
    )
    args = parser.parse_args(argv)

    if args.list_devices:
        if any((args.source, args.device_id, args.backup_root, args.device_name)):
            parser.error("--list-devices cannot be combined with backup options")
        try:
            devices = _device_adapter().discover()
        except Exception as exc:
            print(f"Device discovery failed: {exc}", file=sys.stderr)
            return 1
        if not devices:
            print("No connected iPhones found.")
            return 0
        for device in devices:
            print(f"{device.identifier}\t{device.name}")
        return 0

    if args.source is not None and args.device_id is not None:
        parser.error("choose either --source or --device-id, not both")
    if args.source is None and args.device_id is None:
        parser.error("provide one of --source or --device-id (or use --list-devices)")
    if args.backup_root is None:
        parser.error("--backup-root is required for a backup")
    if args.device_id is not None and args.device_name is not None:
        parser.error("--device-name can only be used with --source")

    try:
        if args.source is not None:
            result = backup_directory(
                args.source,
                args.backup_root,
                device_name=args.device_name or "Local test source",
            )
        else:
            adapter = _device_adapter()
            device = next(
                (
                    candidate
                    for candidate in adapter.discover()
                    if candidate.identifier == args.device_id
                ),
                None,
            )
            if device is None:
                raise RuntimeError(
                    f"No connected iPhone has identifier {args.device_id!r}. "
                    "Use --list-devices to inspect connected devices."
                )
            result = backup_device(adapter, device, args.backup_root)
    except KeyboardInterrupt:
        print(
            "Backup interrupted; any created snapshot remains incomplete.",
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1

    return _print_backup_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
