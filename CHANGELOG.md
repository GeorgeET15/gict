# Changelog

All notable changes to GICT are documented in this file.

## 1.0.0

First production release.

- SHA-256 verified, non-destructive copying of local directories and Linux
  iPhone media into timestamped, report-backed snapshots.
- Linux iPhone device access through `ifuse`, validated against a physical
  iPhone.
- Command renamed from `gict-dev` to `gict`.
- Removed the macOS device adapter. GICT is Linux-only for now; Windows
  support may be added later.
