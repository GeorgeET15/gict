import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Input, OptionList

from gict.devices import DeviceInfo
from gict.screens import (
    AboutScreen,
    ConfirmScreen,
    DependencyCheck,
    DetailedInstructionsScreen,
    DeviceDiscoveryScreen,
    HomeScreen,
    LocalBackupFormScreen,
    PreviousBackupsScreen,
    ProgressScreen,
    ResultsScreen,
    SetupScreen,
)
from gict.tui import GictApp


def _select(app, option_id: str) -> None:
    menu = app.screen.query_one("#home-menu", OptionList)
    for index in range(menu.option_count):
        if menu.get_option_at_index(index).id == option_id:
            menu.highlighted = index
            return
    raise AssertionError(f"no home menu option with id {option_id!r}")


class HomeScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigates_to_local_backup_about_and_previous_backups(self):
        with patch("sys.platform", "win32"):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, HomeScreen)

                _select(app, "about")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, AboutScreen)
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(app.screen, HomeScreen)

                _select(app, "view-backups")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, PreviousBackupsScreen)
                await pilot.click("#back")
                await pilot.pause()
                self.assertIsInstance(app.screen, HomeScreen)

                _select(app, "backup-local")
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, LocalBackupFormScreen)

    async def test_quit_exits_the_app(self):
        app = GictApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _select(app, "quit")
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(app.is_running)

    async def test_iphone_backup_disabled_on_unsupported_platform(self):
        with patch("sys.platform", "win32"):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                menu = app.screen.query_one("#home-menu", OptionList)
                option = menu.get_option(menu.get_option_at_index(0).id)
                self.assertEqual(option.id, "backup-iphone")
                self.assertTrue(option.disabled)

                status = app.screen.query_one("#device-status")
                for _ in range(20):
                    await pilot.pause(0.02)
                    if "checking" not in str(status.render()):
                        break
                self.assertIn("setup incomplete", str(status.render()))


class DeviceDiscoveryScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_shows_no_devices_found_with_retry_and_back(self):
        with patch("gict.screens._device_adapter") as adapter_factory:
            adapter_factory.return_value.discover.return_value = []
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(DeviceDiscoveryScreen())
                await pilot.pause(0.1)
                status = app.screen.query_one("#discovery-status")
                self.assertIn("No connected iPhones found", str(status.render()))
                self.assertFalse(app.screen.query_one("#retry", Button).disabled)
                await pilot.click("#back")
                await pilot.pause()
                self.assertIsInstance(app.screen, HomeScreen)

    async def test_shows_dependency_error_from_real_adapter_message(self):
        with patch("gict.screens._device_adapter") as adapter_factory:
            adapter_factory.return_value.discover.side_effect = RuntimeError(
                "Missing required Linux dependency: ifuse"
            )
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(DeviceDiscoveryScreen())
                await pilot.pause(0.1)
                status = app.screen.query_one("#discovery-status")
                self.assertIn("Missing required Linux dependency: ifuse", str(status.render()))
                self.assertFalse(app.screen.query_one("#retry", Button).disabled)

    async def test_multiple_devices_are_listed_and_none_is_auto_selected(self):
        devices = [
            DeviceInfo("id-1", "Phone One", "linux"),
            DeviceInfo("id-2", "Phone Two", "linux"),
        ]
        with patch("gict.screens._device_adapter") as adapter_factory:
            adapter_factory.return_value.discover.return_value = devices
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(DeviceDiscoveryScreen())
                await pilot.pause(0.1)
                option_list = app.screen.query_one("#device-list", OptionList)
                self.assertEqual(option_list.option_count, 2)
                self.assertIsNone(option_list.highlighted)

                option_list.highlighted = 1
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ConfirmScreen)
                self.assertEqual(app.screen.device.identifier, "id-2")


class ConfirmationGatingTests(unittest.IsolatedAsyncioTestCase):
    async def test_device_backup_not_started_before_confirm_pressed(self):
        device = DeviceInfo("id-1", "Phone One", "linux")
        with patch("gict.screens.backup_device") as backup_device_mock:
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(ConfirmScreen(mode="device", device=device))
                await pilot.pause()
                backup_device_mock.assert_not_called()

                await pilot.click("#back")
                await pilot.pause()
                backup_device_mock.assert_not_called()

    async def test_confirm_starts_backup_with_chosen_destination(self):
        device = DeviceInfo("id-1", "Phone One", "linux")
        with patch("gict.screens.backup_device") as backup_device_mock:
            backup_device_mock.return_value = {
                "status": "COMPLETE",
                "files_found": 0,
                "files_copied": 0,
                "files_verified": 0,
                "errors": [],
                "snapshot": "/tmp/snapshot",
                "report_path": "/tmp/snapshot/report.json",
            }
            with patch("gict.screens._device_adapter") as adapter_factory:
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(ConfirmScreen(mode="device", device=device))
                    await pilot.pause()
                    app.screen.query_one("#backup-root-input", Input).value = "/tmp/chosen-root"
                    await pilot.click("#confirm")
                    for _ in range(20):
                        await pilot.pause(0.05)
                        if isinstance(app.screen, ResultsScreen):
                            break
                    self.assertIsInstance(app.screen, ResultsScreen)
                    backup_device_mock.assert_called_once()
                    _, args, kwargs = backup_device_mock.mock_calls[0]
                    self.assertEqual(args[2], "/tmp/chosen-root")


class LocalBackupFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_missing_source_directory(self):
        app = GictApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(LocalBackupFormScreen())
            await pilot.pause()
            app.screen.query_one("#source-input", Input).value = "/definitely/not/a/real/path"
            await pilot.click("#continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, LocalBackupFormScreen)
            error = app.screen.query_one("#form-error")
            self.assertIn("does not exist", str(error.render()))

    async def test_valid_source_proceeds_to_confirm(self):
        with tempfile.TemporaryDirectory() as temp:
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(LocalBackupFormScreen())
                await pilot.pause()
                app.screen.query_one("#source-input", Input).value = temp
                await pilot.click("#continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, ConfirmScreen)
                self.assertEqual(app.screen.source, temp)


class ProgressAndResultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_and_results_reflect_engine_values_not_fabricated(self):
        def fake_backup_directory(source, backup_root, device_name=None, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress({"stage": "scanned", "files_found": 3})
                for index in range(1, 4):
                    on_progress({
                        "stage": "copy",
                        "files_found": 3,
                        "files_copied": index,
                        "current_file": f"file{index}.jpg",
                        "error": None,
                    })
            return {
                "status": "COMPLETE",
                "files_found": 3,
                "files_copied": 3,
                "files_verified": 3,
                "errors": [],
                "snapshot": "/tmp/snap",
                "report_path": "/tmp/snap/report.json",
            }

        with patch("gict.screens.backup_directory", side_effect=fake_backup_directory):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(
                    ProgressScreen(mode="local", source="/tmp/src", backup_root="/tmp/dst")
                )
                for _ in range(20):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ResultsScreen):
                        break
                await pilot.pause()

                self.assertIsInstance(app.screen, ResultsScreen)
                summary = str(app.screen.query_one("#results-summary").render())
                self.assertIn("COMPLETE", summary)
                self.assertIn("Files found: 3", summary)
                self.assertIn("Files copied: 3", summary)
                self.assertIn("Files verified: 3", summary)
                self.assertIn("Errors: 0", summary)


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_sets_event_and_engine_reports_incomplete(self):
        def fake_backup_directory(source, backup_root, device_name=None, **kwargs):
            cancel_event: threading.Event = kwargs["cancel_event"]
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress({"stage": "scanned", "files_found": 5})
            for _ in range(50):
                if cancel_event.is_set():
                    raise KeyboardInterrupt
                threading.Event().wait(0.01)
            return {"status": "COMPLETE", "files_found": 5, "files_copied": 5,
                    "files_verified": 5, "errors": [], "snapshot": "x", "report_path": "y"}

        with patch("gict.screens.backup_directory", side_effect=fake_backup_directory):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(
                    ProgressScreen(mode="local", source="/tmp/src", backup_root="/tmp/dst")
                )
                await pilot.pause(0.05)
                await pilot.click("#cancel")

                for _ in range(40):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ResultsScreen):
                        break
                await pilot.pause()

                self.assertIsInstance(app.screen, ResultsScreen)
                self.assertEqual(app.screen.result["status"], "INCOMPLETE")

    async def test_engine_exception_is_shown_as_incomplete_result(self):
        with patch(
            "gict.screens.backup_directory",
            side_effect=NotADirectoryError("Source directory does not exist: /nope"),
        ):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(
                    ProgressScreen(mode="local", source="/nope", backup_root="/tmp/dst")
                )
                for _ in range(20):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ResultsScreen):
                        break
                await pilot.pause()

                self.assertIsInstance(app.screen, ResultsScreen)
                self.assertEqual(app.screen.result["status"], "INCOMPLETE")
                self.assertIn(
                    "Source directory does not exist",
                    app.screen.result["errors"][0]["error"],
                )


class PreviousBackupsScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_complete_and_malformed_snapshots_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = root / "Phone" / "2026-01-01_120000"
            good.mkdir(parents=True)
            (good / "report.json").write_text(
                json.dumps({
                    "status": "COMPLETE",
                    "files_found": 2,
                    "files_copied": 2,
                    "files_verified": 2,
                }),
                encoding="utf-8",
            )
            (good / "COMPLETE").write_text("COMPLETE\n", encoding="utf-8")

            malformed = root / "Phone" / "2026-01-02_120000"
            malformed.mkdir(parents=True)
            (malformed / "report.json").write_text("not valid json", encoding="utf-8")

            no_report = root / "Phone" / "2026-01-03_120000"
            no_report.mkdir(parents=True)

            with patch("gict.screens.DEFAULT_BACKUP_ROOT", root):
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(PreviousBackupsScreen())
                    await pilot.pause()
                    listing = str(app.screen.query_one("#backups-listing").render())

            self.assertIn("COMPLETE", listing)
            self.assertIn("found 2, copied 2, verified 2", listing)
            self.assertIn("unreadable report", listing)
            self.assertIn("status unknown", listing)
            # Reading the listing must not have written anything into the snapshots.
            self.assertEqual((good / "report.json").read_text(encoding="utf-8").strip()[0], "{")

    async def test_missing_backup_root_shows_clear_message_not_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            missing_root = Path(temp) / "does-not-exist"
            with patch("gict.screens.DEFAULT_BACKUP_ROOT", missing_root):
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(PreviousBackupsScreen())
                    await pilot.pause()
                    listing = str(app.screen.query_one("#backups-listing").render())
            self.assertIn("No backups found yet", listing)


class SetupScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_reachable_from_home_menu(self):
        app = GictApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _select(app, "system-setup")
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupScreen)
            await pilot.click("#back")
            await pilot.pause()
            self.assertIsInstance(app.screen, HomeScreen)

    async def test_shows_every_mocked_dependency_status(self):
        checks = [
            DependencyCheck("Linux operating system", "available", "Linux detected"),
            DependencyCheck("ifuse", "incompatible", "found 1.2.2, need 1.2.1"),
            DependencyCheck("idevice_id", "missing", "not found"),
            DependencyCheck("mountpoint", "unknown", "could not determine"),
        ]
        with patch("gict.screens.check_iphone_dependencies", return_value=checks):
            with patch("gict.screens.overall_status", return_value="Setup incomplete"):
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(SetupScreen())
                    await pilot.pause(0.1)
                    text = str(app.screen.query_one("#setup-checks").render())

        self.assertIn("OK - Linux operating system", text)
        self.assertIn("INCOMPATIBLE - ifuse", text)
        self.assertIn("MISSING - idevice_id", text)
        self.assertIn("UNKNOWN - mountpoint", text)

    async def test_install_command_shown_and_copy_enabled_only_when_incomplete(self):
        incomplete = [DependencyCheck("ifuse", "missing", "not found")]
        with patch("gict.screens.check_iphone_dependencies", return_value=incomplete):
            with patch("gict.screens.detect_distro", return_value="debian"):
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.push_screen(SetupScreen())
                    await pilot.pause(0.1)
                    install_text = str(app.screen.query_one("#setup-install").render())
                    self.assertIn("apt install", install_text)
                    self.assertIn("not a guaranteed package name", install_text)
                    self.assertFalse(app.screen.query_one("#copy-command", Button).disabled)

    async def test_copy_command_disabled_and_no_install_text_when_ready(self):
        ready = [DependencyCheck("ifuse", "available", "ifuse 1.2.1")]
        with patch("gict.screens.check_iphone_dependencies", return_value=ready):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SetupScreen())
                await pilot.pause(0.1)
                self.assertTrue(app.screen.query_one("#copy-command", Button).disabled)
                install_text = str(app.screen.query_one("#setup-install").render())
                self.assertEqual(install_text.strip(), "")

    async def test_recheck_button_reruns_the_dependency_check(self):
        ready = [DependencyCheck("ifuse", "available", "ifuse 1.2.1")]
        with patch(
            "gict.screens.check_iphone_dependencies", return_value=ready
        ) as checker:
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SetupScreen())
                await pilot.pause(0.1)
                # Home screen's own status check also calls the mocked
                # function once, so only assert the delta from Recheck.
                baseline = checker.call_count
                await pilot.click("#recheck")
                await pilot.pause(0.1)
                self.assertEqual(checker.call_count, baseline + 1)

    async def test_view_detailed_instructions_lists_all_distros(self):
        app = GictApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(SetupScreen())
            await pilot.pause(0.1)
            await pilot.click("#view-details")
            await pilot.pause()
            self.assertIsInstance(app.screen, DetailedInstructionsScreen)
            text = str(app.screen.query_one("#detailed-instructions-text").render())
            self.assertIn("apt install", text)
            self.assertIn("dnf install", text)
            self.assertIn("pacman -S", text)
            await pilot.click("#back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupScreen)

    async def test_missing_iphone_dependencies_do_not_block_local_backup(self):
        missing = [
            DependencyCheck("ifuse", "missing", "not found"),
            DependencyCheck("idevice_id", "missing", "not found"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            with patch("gict.screens.check_iphone_dependencies", return_value=missing):
                app = GictApp()
                async with app.run_test() as pilot:
                    await pilot.pause(0.1)
                    _select(app, "backup-local")
                    await pilot.press("enter")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, LocalBackupFormScreen)

                    app.screen.query_one("#source-input", Input).value = temp
                    await pilot.click("#continue")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, ConfirmScreen)

    async def test_non_linux_platform_shows_clear_status_without_crashing(self):
        with patch("sys.platform", "darwin"):
            app = GictApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(SetupScreen())
                for _ in range(20):
                    await pilot.pause(0.02)
                    text = str(app.screen.query_one("#setup-checks").render())
                    if "checking" not in text.lower() and text.strip():
                        break
                self.assertIn("incompatible", text.lower())
                self.assertIn("darwin", text.lower())


if __name__ == "__main__":
    unittest.main()
