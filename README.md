# GICT - George's iPhone Copy Tool

A simple Linux CLI tool for backing up iPhone photos and videos.

GICT copies your media into timestamped snapshots, verifies every copied file using SHA-256, and generates a report for each backup.

## Features

- Verified file copying
- Organized photos and videos
- Timestamped backups
- Reports for successful and incomplete backups
- Safe, read-only iPhone access

## Requirements

- Linux
- Python 3.10+
- For iPhone backups: `ifuse` 1.2.1, `idevice_id`, `ideviceinfo`, `mountpoint`, and `fusermount3` or `fusermount`

Local-directory backups don't require an iPhone or the device-access tools.

## Installation

Install using [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/GeorgeET15/gict-portable.git
```

Check the installation:

```bash
gict --version
```

## Usage

**Back up a connected iPhone**

Unlock your iPhone, connect it over USB, and trust the computer when prompted.

List connected devices:

```bash
gict --list-devices
```

Back up a specific device:

```bash
gict --device-id DEVICE_ID --backup-root ~/GICT_Backups
```

Replace `DEVICE_ID` with the identifier shown by the previous command.

**Back up a local directory**

```bash
gict --source ./photos --backup-root ~/GICT_Backups
```

## Backup output

Each run creates a timestamped snapshot containing your media, a `report.json`, and a status marker.

```text
GICT_Backups/
└── iPhone/
    └── 2026-10-21_103000/
        ├── photos/
        ├── videos/
        ├── other/
        ├── report.json
        └── COMPLETE
```

Every copied file is SHA-256 verified. If a backup fails or is interrupted, its snapshot is marked `INCOMPLETE` when a snapshot has been created.

**Important:** Keep another copy of your media. GICT should not be your only backup.

## Development

```bash
git clone https://github.com/GeorgeET15/gict-portable.git
cd gict-portable
python -m pip install -e .
python -m pytest
```

## Limitations

iPhone device access is currently supported only on Linux. Windows support may come later; macOS support is not planned.