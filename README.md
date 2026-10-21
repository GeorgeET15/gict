# GICT - George's iPhone Copy Tool

A simple Linux tool for backing up iPhone photos and videos, with an
interactive terminal interface.

GICT copies your media into timestamped snapshots, verifies every copied file using SHA-256, and generates a report for each backup.

## Features

- Interactive terminal interface, launched by running `gict`
- A built-in System Setup screen that checks iPhone-access requirements
  individually and shows guided install commands
- Verified file copying
- Organized photos and videos
- Timestamped backups
- Reports for successful and incomplete backups
- Safe, read-only iPhone access
- Non-interactive flags for scripting and automation

## Requirements

- Linux
- Python 3.10+
- [`textual`](https://textual.textualize.io/) (installed automatically as a dependency)
- For iPhone backups: `ifuse` exactly version 1.2.1, `idevice_id`, `ideviceinfo`, `mountpoint`, and `fusermount3` or `fusermount`

Local-directory backups don't require an iPhone or the device-access tools.
GICT never installs anything itself; it only checks what's already on your
system and shows you the commands to run yourself.

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

### Interactive mode

Running `gict` with no arguments launches the interactive terminal interface:

```bash
gict
```

From the home screen you can:

- Back up an iPhone (discovers connected devices, lets you pick one, choose a
  destination, and confirm before anything is mounted or copied)
- Back up a local directory (prompts for a source, destination, and display
  name)
- View previous backups (reads existing `report.json`/status-marker files
  under `~/GICT_Backups`, read-only)
- System Setup (checks whether `ifuse`, `idevice_id`, `ideviceinfo`,
  `mountpoint`, and `fusermount3`/`fusermount` are installed and compatible,
  one by one, and shows an example install command for your detected Linux
  distribution)
- View information about GICT

Navigate with the arrow keys and Enter; press Escape or use the on-screen
Back button to go back a screen. Nothing is mounted, copied, or overwritten
until you explicitly confirm on the confirmation screen.

### Setting up iPhone access

Open **System Setup** from the home screen at any time to see exactly which
iPhone-access requirement is missing or incompatible, with an example
install command for Debian/Ubuntu, Fedora, or Arch Linux if your
distribution is detected. GICT never runs that command for you, and
installing the distribution's package is not guaranteed to provide the
exact `ifuse` 1.2.1 version GICT requires; use Recheck on that screen to
confirm after installing. You're always free to use local-directory mode
without doing any of this.

### Non-interactive mode (scripting)

Passing any flag skips the interactive interface and runs the original
flag-driven behavior, unchanged, for use in scripts and automation:

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

Each run creates a timestamped snapshot containing your media, a `report.json`, and a status marker. Photos and videos are grouped by their original modification date; the original folder they came from (for example an iPhone's `100APPLE`/`101APPLE` DCIM folders) is not preserved, only the filename.

```text
GICT_Backups/
└── iPhone/
    └── 2026-10-21_103000/
        ├── photos/
        │   └── 2026/
        │       └── 10/
        │           └── IMG_1234.HEIC
        ├── videos/
        │   └── 2026/
        │       └── 10/
        │           └── IMG_5678.MOV
        ├── other/
        │   └── metadata.dat
        ├── report.json
        └── COMPLETE
```

If two different source folders contain files with the same name (common with iPhone DCIM folders after the camera roll resets its numbering), the second one is kept under a renamed filename, such as `IMG_1234_1.HEIC`, rather than overwriting the first.

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