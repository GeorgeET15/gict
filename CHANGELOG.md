# Changelog

All notable changes to GICT are documented in this file.

## Unreleased

Added a System Setup screen to the TUI, reachable from the home screen, for
checking iPhone-access requirements.

- Checks Linux OS, Python version, `ifuse` (exact version 1.2.1, reusing the
  existing `LinuxDeviceAdapter._verify_ifuse` check with no duplicated
  version logic), `idevice_id`, `ideviceinfo`, `mountpoint`, and
  `fusermount3`/`fusermount` individually, each reported as available,
  missing, incompatible, or unable to determine.
- Detects the Linux distribution from `/etc/os-release` (Debian/Ubuntu,
  Fedora, Arch, or unknown) and shows an example install command, with an
  explicit note that package names/versions vary and that installing the
  distribution's package does not guarantee the exact `ifuse` 1.2.1 version
  GICT requires.
- Never runs an installation command itself; only displays it, with a
  best-effort "Copy command" action and a "Recheck" action.
- The home screen's status line now reuses the same check, replacing the
  previous first-failure-only message.
- Local-directory backup mode remains fully usable when none of these
  dependencies are present.
- New module: `src/gict/setup_check.py` (no new dependency).

## 1.1.0

Added an interactive terminal interface (Textual). Running `gict` with no
arguments now launches it; every existing flag-driven command is unchanged
and still works exactly as before for scripting.

- Home screen with iPhone backup, local-directory backup, previous-backups
  browser, and About actions.
- iPhone backup flow: device discovery, explicit device selection (never
  automatic), destination confirmation, and a live progress screen before
  anything is mounted or copied.
- Local-directory backup flow with source/destination validation.
- Live progress (files found/copied/verified, current file, elapsed time,
  errors) backed by a new optional, backward-compatible `on_progress`/
  `cancel_event` hook on `backup_directory()`/`backup_device()`; the rest of
  the backup engine (`integrity.py`, `snapshots.py`, `devices/`) is
  unchanged.
- Read-only previous-backups browser that reads existing reports/markers
  under the backup root without modifying them.
- New dependency: `textual`.
- Destination filenames under `photos/`, `videos/`, and `other/` no longer
  preserve the original source subfolder (for example an iPhone's
  `100APPLE`/`101APPLE`); only the filename is kept. If two source files
  from different folders share a filename, the later one is copied under a
  renamed filename (for example `IMG_1234_1.HEIC`) instead of overwriting
  the earlier one.

## 1.0.0

First production release.

- SHA-256 verified, non-destructive copying of local directories and Linux
  iPhone media into timestamped, report-backed snapshots.
- Linux iPhone device access through `ifuse`, validated against a physical
  iPhone.
- Command renamed from `gict-dev` to `gict`.
- Removed the macOS device adapter. GICT is Linux-only for now; Windows
  support may be added later.
