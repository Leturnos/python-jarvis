from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from core.ui.main_window import MainWindow


def test_main_window_tabs_structure():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)

    assert window.windowTitle() == "Painel do Jarvis"
    assert window.stacked_widget.count() == 3
    assert "status" in window.pivot.items
    assert "history" in window.pivot.items
    assert "settings" in window.pivot.items
    assert window.pivot.items["status"].text() == "Status"
    assert window.pivot.items["history"].text() == "Histórico"
    assert window.pivot.items["settings"].text() == "Configurações"
