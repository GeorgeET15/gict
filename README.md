# GICT — George's iPhone Copy Tool

GICT is a planned cross-platform iPhone media copier for Linux, macOS,
and Windows.

## Project status

Early development. The portable package and device-access adapters are
not yet complete. Do not use this development package to back up an iPhone.

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

The development command intentionally does not perform backups yet.
