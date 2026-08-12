from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from core.ui.app_controller import QtAppController


def test_app_controller_initialization():
    app = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    tray_adapter = MagicMock()

    controller = QtAppController(app, ui_adapter, tray_adapter)

    assert controller.voice_overlay is not None
    assert hasattr(controller, "voice_overlay")
