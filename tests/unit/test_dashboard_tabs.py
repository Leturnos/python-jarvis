from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from core.ui.main_window import MainWindow


def test_main_window_tabs_structure():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)

    assert window.stacked_widget.count() == 3
    assert "Status" in window.pivot.items
    assert "History" in window.pivot.items
    assert "Settings" in window.pivot.items
