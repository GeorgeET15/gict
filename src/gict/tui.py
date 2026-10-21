"""Interactive terminal interface for GICT."""

from textual.app import App

from gict.screens import HomeScreen


class GictApp(App):
    """GICT's interactive terminal application."""

    TITLE = "GICT - George's iPhone Copy Tool"
    CSS = """
    Screen {
        align: center middle;
    }

    #home-body, #discovery-body, #form-body, #confirm-body, #progress-body,
    #results-body, #setup-body {
        width: 90%;
        max-width: 110;
        height: auto;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def return_home(self) -> None:
        """Reset the screen stack and show a fresh Home screen."""
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self.push_screen(HomeScreen())


def run() -> int:
    """Launch the interactive GICT application."""
    GictApp().run()
    return 0
