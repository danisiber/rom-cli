"""User interface module (CLI menu and Textual TUI)."""

from rom.ui.menu import select_menu, show
from rom.ui.tui import run_tui


def _has_textual():
    try:
        import textual  # noqa: F401
        return True
    except Exception:
        return False


__all__ = ["select_menu", "show", "run_tui", "_has_textual"]
