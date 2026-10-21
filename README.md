# GICT — George's iPhone Copy Tool

GICT is an experimental Python backup tool. Cross-platform iPhone support is a
goal, not a current support claim.

## Project status

Early development. The local-directory workflow is tested with temporary data.
Linux and macOS `ifuse` adapters are implemented and mock-tested, but neither
has been validated with a physical iPhone; the macOS adapter has not been run on
macOS. Windows device access is not implemented. Do not rely on this development
package as the only copy of iPhone media.

## Design goals

- Non-destructive copying of iPhone media.
- SHA-256 verification of each completed destination file.
- Timestamped snapshots and machine-readable reports.
- Explicit incomplete status after interrupted or failed backups.
- Platform-specific iPhone access with shared portable copying logic.

## Development

Requires Python 3.10 or newer.

```bash
python -m pip install -e .
gict-dev --version
```

To test with disposable local files, provide an explicit source directory and
backup root:

```bash
gict-dev --source ./test-source --backup-root ./test-backups --device-name "Test Phone"
```

The command never falls back to device access. A completed run reports the
verified file count and snapshot paths; failures return a nonzero exit code and
leave the snapshot marked incomplete.

### Experimental Linux device access

Linux device access requires `ifuse` 1.2.1, `idevice_id`, `ideviceinfo`,
`mountpoint`, and either `fusermount3` or `fusermount` on `PATH`. Install these
tools using your Linux distribution's package manager, and pair/trust the
iPhone with the computer first.

```bash
gict-dev --list-devices
gict-dev --device-id DEVICE_ID --backup-root ./GICT_Backups
```

Device backups are opt-in by identifier, mount the media filesystem read-only,
and use only a fresh mount created by GICT. Automated tests mock all device and
mount commands; no physical-device workflow has been validated yet.

### Experimental macOS device access

The macOS adapter uses upstream `ifuse` with macFUSE; this is not an Apple
supported or endorsed interface. Building `ifuse` on macOS requires Xcode
Command Line Tools, `autoconf`, `automake`, `libtool`, and the upstream
libimobiledevice dependencies (`libplist`, `libimobiledevice-glue`, `libusbmuxd`,
and `libimobiledevice`). Install macFUSE separately. Depending on its backend
and macOS version, macFUSE may require approval in Privacy & Security and a
restart. Follow the current [ifuse macOS build instructions](https://github.com/libimobiledevice/ifuse#macos)
and [macFUSE installation guide](https://github.com/macfuse/macfuse/wiki/Getting-Started).

The macOS adapter is only mock-tested on Linux and has not been run on macOS or
with an iPhone. It is experimental, not a verified macOS support claim. Windows
device access is unavailable.
