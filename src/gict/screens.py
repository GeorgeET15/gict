"""Screens for the GICT interactive terminal interface."""

import json
import sys
import threading
import time
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, OptionList, ProgressBar, Static
from textual.widgets.option_list import Option

from gict import __version__
from gict.backup import backup_device, backup_directory
from gict.cli import _device_adapter

DEFAULT_BACKUP_ROOT = Path.home() / "GICT_Backups"


class HomeScreen(Screen):
    """Landing screen: menu plus contextual status."""

    def compose(self) -> ComposeResult:
        iphone_supported = sys.platform == "linux"
        yield Header()
        yield Vertical(
            Static(f"Backup directory: {DEFAULT_BACKUP_ROOT}", id="backup-root-info"),
            Static(
                "iPhone device access: checking..."
                if iphone_supported
                else "iPhone device access: unavailable (Linux only)",
                id="device-status",
            ),
            OptionList(
                Option("Back up an iPhone", id="backup-iphone", disabled=not iphone_supported),
                Option("Back up a local directory", id="backup-local"),
                Option("View previous backups", id="view-backups"),
                Option("About GICT", id="about"),
                Option("Quit", id="quit"),
                id="home-menu",
            ),
            id="home-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        if sys.platform == "linux":
            self.run_worker(self._check_device_status, thread=True)

    def _check_device_status(self) -> None:
        try:
            adapter = _device_adapter()
            adapter._executables()
        except RuntimeError as exc:
            self.app.call_from_thread(
                self._set_device_status, f"iPhone device access: not ready ({exc})"
            )
            return
        self.app.call_from_thread(self._set_device_status, "iPhone device access: ready")

    def _set_device_status(self, text: str) -> None:
        self.query_one("#device-status", Static).update(text)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id == "backup-iphone":
            self.app.push_screen(DeviceDiscoveryScreen())
        elif option_id == "backup-local":
            self.app.push_screen(LocalBackupFormScreen())
        elif option_id == "view-backups":
            self.app.push_screen(PreviousBackupsScreen())
        elif option_id == "about":
            self.app.push_screen(AboutScreen())
        elif option_id == "quit":
            self.app.exit()


class DeviceDiscoveryScreen(Screen):
    """Discovers connected iPhones and lets the user pick one."""

    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._devices: list = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("Discovering connected iPhones...", id="discovery-status"),
            OptionList(id="device-list"),
            Horizontal(
                Button("Retry", id="retry", disabled=True),
                Button("Back", id="back"),
            ),
            id="discovery-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._discover()

    def _discover(self) -> None:
        self.query_one("#discovery-status", Static).update("Discovering connected iPhones...")
        self.query_one("#device-list", OptionList).clear_options()
        self.query_one("#retry", Button).disabled = True
        self.run_worker(self._discover_worker, thread=True)

    def _discover_worker(self) -> None:
        try:
            adapter = _device_adapter()
            devices = adapter.discover()
        except Exception as exc:
            self.app.call_from_thread(self._show_error, str(exc))
            return
        self.app.call_from_thread(self._show_devices, devices)

    def _show_error(self, message: str) -> None:
        self.query_one("#discovery-status", Static).update(
            f"Could not discover iPhones: {message}"
        )
        self.query_one("#retry", Button).disabled = False

    def _show_devices(self, devices: list) -> None:
        self._devices = devices
        if not devices:
            self.query_one("#discovery-status", Static).update(
                "No connected iPhones found. Unlock the iPhone, connect it by "
                "USB, and trust this computer if prompted, then retry."
            )
            self.query_one("#retry", Button).disabled = False
            return

        self.query_one("#discovery-status", Static).update(
            f"Found {len(devices)} device(s). Select one to back up:"
        )
        option_list = self.query_one("#device-list", OptionList)
        for device in devices:
            option_list.add_option(
                Option(f"{device.name} ({device.identifier})", id=device.identifier)
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "retry":
            self._discover()
        elif event.button.id == "back":
            self.app.pop_screen()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        device = next(d for d in self._devices if d.identifier == event.option.id)
        self.app.push_screen(ConfirmScreen(mode="device", device=device))

    def action_go_back(self) -> None:
        self.app.pop_screen()


class LocalBackupFormScreen(Screen):
    """Prompts for a local-directory backup's source, destination, and name."""

    BINDINGS = [("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("Back up a local directory", id="form-title"),
            Static("Source directory:"),
            Input(placeholder="/path/to/source", id="source-input"),
            Static("Backup destination:"),
            Input(value=str(DEFAULT_BACKUP_ROOT), id="root-input"),
            Static("Display name:"),
            Input(value="Local test source", id="name-input"),
            Static("", id="form-error"),
            Horizontal(
                Button("Continue", id="continue", variant="primary"),
                Button("Back", id="back"),
            ),
            id="form-body",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
            return
        if event.button.id != "continue":
            return

        error_widget = self.query_one("#form-error", Static)
        source = self.query_one("#source-input", Input).value.strip()
        backup_root = self.query_one("#root-input", Input).value.strip()
        device_name = self.query_one("#name-input", Input).value.strip() or "Local test source"

        if not source:
            error_widget.update("Source directory is required.")
            return
        source_path = Path(source).expanduser()
        if not source_path.is_dir():
            error_widget.update(f"Source directory does not exist: {source_path}")
            return
        if not backup_root:
            error_widget.update("Backup destination is required.")
            return

        error_widget.update("")
        self.app.push_screen(
            ConfirmScreen(
                mode="local",
                source=str(source_path),
                device_name=device_name,
                backup_root=str(Path(backup_root).expanduser()),
            )
        )

    def action_go_back(self) -> None:
        self.app.pop_screen()


class ConfirmScreen(Screen):
    """Shows exactly what will run, and lets the user pick/confirm the destination."""

    def __init__(
        self,
        mode: str,
        *,
        device=None,
        source: str | None = None,
        device_name: str | None = None,
        backup_root: str | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.device = device
        self.source = source
        self.device_name = device_name
        self._initial_backup_root = backup_root or str(DEFAULT_BACKUP_ROOT)

    def compose(self) -> ComposeResult:
        yield Header()
        if self.mode == "device":
            summary = f"Device: {self.device.name} ({self.device.identifier})"
        else:
            summary = f"Source: {self.source}\nDisplay name: {self.device_name}"
        yield Vertical(
            Static("Confirm backup", id="confirm-title"),
            Static(summary, id="confirm-summary"),
            Static("Backup destination:"),
            Input(value=self._initial_backup_root, id="backup-root-input"),
            Static("", id="confirm-error"),
            Horizontal(
                Button("Confirm", id="confirm", variant="primary"),
                Button("Back", id="back"),
            ),
            id="confirm-body",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
            return
        if event.button.id != "confirm":
            return

        backup_root = self.query_one("#backup-root-input", Input).value.strip()
        if not backup_root:
            self.query_one("#confirm-error", Static).update("Backup destination is required.")
            return

        self.app.push_screen(
            ProgressScreen(
                mode=self.mode,
                device=self.device,
                source=self.source,
                device_name=self.device_name,
                backup_root=str(Path(backup_root).expanduser()),
            )
        )


class ProgressScreen(Screen):
    """Runs the existing backup engine in a worker thread and shows live progress."""

    def __init__(
        self,
        mode: str,
        *,
        device=None,
        source: str | None = None,
        device_name: str | None = None,
        backup_root: str = "",
    ) -> None:
        super().__init__()
        self.mode = mode
        self.device = device
        self.source = source
        self.device_name = device_name
        self.backup_root = backup_root
        self.cancel_event = threading.Event()
        self._start_time = 0.0
        self._files_found = 0
        self._files_copied = 0
        self._error_count = 0
        self._current_file = ""

    def compose(self) -> ComposeResult:
        yield Header()
        if self.mode == "device":
            target = f"Device: {self.device.name}  ->  {self.backup_root}"
        else:
            target = f"Source: {self.source}  ->  {self.backup_root}"
        yield Vertical(
            Static(target, id="progress-target"),
            Static("Starting...", id="progress-status"),
            ProgressBar(total=None, id="progress-bar", show_eta=False),
            Static("", id="progress-detail"),
            Button("Cancel", id="cancel"),
            id="progress-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._start_time = time.monotonic()
        self.set_interval(1.0, self._tick_elapsed)
        self.run_worker(self._run_backup, thread=True)

    def _tick_elapsed(self) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        self.query_one("#progress-status", Static).update(
            f"Copied {self._files_copied}/{self._files_found} files "
            f"| Errors: {self._error_count} | Elapsed: {elapsed}s"
        )

    def _on_progress(self, event: dict) -> None:
        self.app.call_from_thread(self._apply_progress, event)

    def _apply_progress(self, event: dict) -> None:
        bar = self.query_one("#progress-bar", ProgressBar)
        if event["stage"] == "scanned":
            self._files_found = event["files_found"]
            if self._files_found:
                bar.update(total=self._files_found)
        elif event["stage"] == "copy":
            self._files_found = event["files_found"]
            self._files_copied = event["files_copied"]
            self._current_file = event["current_file"]
            if event["error"]:
                self._error_count += 1
            bar.update(progress=self._files_copied)
            self.query_one("#progress-detail", Static).update(
                f"Current file: {self._current_file}"
            )

    def _run_backup(self) -> None:
        try:
            if self.mode == "device":
                adapter = _device_adapter()
                result = backup_device(
                    adapter,
                    self.device,
                    self.backup_root,
                    on_progress=self._on_progress,
                    cancel_event=self.cancel_event,
                )
            else:
                result = backup_directory(
                    self.source,
                    self.backup_root,
                    self.device_name,
                    on_progress=self._on_progress,
                    cancel_event=self.cancel_event,
                )
        except KeyboardInterrupt:
            self.app.call_from_thread(
                self._finish_with_error,
                "Backup cancelled; snapshot marked incomplete.",
            )
            return
        except Exception as exc:
            self.app.call_from_thread(self._finish_with_error, str(exc))
            return
        self.app.call_from_thread(self._finish, result)

    def _finish(self, result: dict) -> None:
        self.app.pop_screen()
        self.app.push_screen(ResultsScreen(result))

    def _finish_with_error(self, message: str) -> None:
        self.app.pop_screen()
        self.app.push_screen(
            ResultsScreen(
                {
                    "status": "INCOMPLETE",
                    "files_found": self._files_found,
                    "files_copied": self._files_copied,
                    "files_verified": self._files_copied,
                    "errors": [{"stage": "backup", "error": message}],
                    "snapshot": "(see backup directory)",
                    "report_path": "(see backup directory)",
                }
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.cancel_event.set()
            event.button.disabled = True
            self.query_one("#progress-status", Static).update("Cancelling...")


class ResultsScreen(Screen):
    """Shows the final outcome of a backup."""

    def __init__(self, result: dict) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        yield Header()
        status = self.result.get("status", "UNKNOWN")
        lines = [
            f"Status: {status}",
            f"Files found: {self.result.get('files_found', 0)}",
            f"Files copied: {self.result.get('files_copied', 0)}",
            f"Files verified: {self.result.get('files_verified', 0)}",
            f"Errors: {len(self.result.get('errors', []))}",
            f"Snapshot: {self.result.get('snapshot', '(unknown)')}",
            f"Report: {self.result.get('report_path', '(unknown)')}",
        ]
        yield Vertical(
            Static(
                "Backup complete" if status == "COMPLETE" else "Backup incomplete",
                id="results-title",
            ),
            Static("\n".join(lines), id="results-summary"),
            Horizontal(
                Button("Home", id="home"),
                Button("View report", id="view-report"),
                Button("Start another backup", id="another"),
                Button("Exit", id="exit"),
            ),
            id="results-body",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("home", "another"):
            self.app.return_home()
        elif event.button.id == "view-report":
            self.app.push_screen(ReportViewScreen(self.result.get("report_path")))
        elif event.button.id == "exit":
            self.app.exit()


class ReportViewScreen(Screen):
    """Displays a snapshot's report.json read-only."""

    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, report_path) -> None:
        super().__init__()
        self.report_path = report_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(Static(self._load_report_text(), id="report-text"))
        yield Button("Back", id="back")
        yield Footer()

    def _load_report_text(self) -> str:
        try:
            return Path(self.report_path).read_text(encoding="utf-8")
        except (OSError, TypeError) as exc:
            return f"Could not read report: {exc}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()


class PreviousBackupsScreen(Screen):
    """Read-only browser for snapshots under the configured backup root."""

    BINDINGS = [("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(Static(self._build_listing(), id="backups-listing"))
        yield Button("Back", id="back")
        yield Footer()

    def _build_listing(self) -> str:
        root = DEFAULT_BACKUP_ROOT
        if not root.is_dir():
            return f"No backups found yet. Backup directory does not exist: {root}"

        try:
            device_dirs = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError as exc:
            return f"Could not read backup directory: {exc}"

        if not device_dirs:
            return f"No backups found yet in {root}."

        lines = []
        for device_dir in device_dirs:
            try:
                snapshot_dirs = sorted(p for p in device_dir.iterdir() if p.is_dir())
            except OSError as exc:
                lines.append(f"{device_dir.name}: could not read ({exc})")
                continue
            for snapshot_dir in snapshot_dirs:
                lines.append(self._describe_snapshot(device_dir.name, snapshot_dir))

        return "\n".join(lines) if lines else f"No backups found yet in {root}."

    def _describe_snapshot(self, device_name: str, snapshot_dir: Path) -> str:
        timestamp = snapshot_dir.name
        report_path = snapshot_dir / "report.json"

        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return f"{device_name} | {timestamp} | status unknown (unreadable report)"
            status = report.get("status", "UNKNOWN")
            found = report.get("files_found", "?")
            copied = report.get("files_copied", "?")
            verified = report.get("files_verified", "?")
            return (
                f"{device_name} | {timestamp} | {status} | "
                f"found {found}, copied {copied}, verified {verified}"
            )

        if (snapshot_dir / "COMPLETE").exists():
            return f"{device_name} | {timestamp} | COMPLETE (no report.json found)"
        if (snapshot_dir / "INCOMPLETE").exists():
            return f"{device_name} | {timestamp} | INCOMPLETE (no report.json found)"
        return f"{device_name} | {timestamp} | status unknown (no report or marker found)"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()


class AboutScreen(Screen):
    """Static information about GICT."""

    BINDINGS = [("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f"GICT - George's iPhone Copy Tool\nVersion {__version__}\n\n"
            "Non-destructive, SHA-256 verified backups of iPhone media and "
            "local directories.\n\n"
            "iPhone device access is currently supported only on Linux.\n"
            "License: MIT.",
            id="about-text",
        )
        yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()
