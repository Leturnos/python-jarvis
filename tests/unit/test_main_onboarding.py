from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from core.ui.app_controller import QtAppController


def test_onboarding_mode_triggers_settings_tab_focus():
    app = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()
    tray_adapter = MagicMock()

    with patch("core.ui.app_controller.InfoBar.warning") as mock_warning:
        with patch(
            "core.ui.app_controller.config", {"llm": {"active_provider": "gemini"}}
        ):
            controller = QtAppController(app, ui_adapter, tray_adapter, onboarding=True)

            assert controller.main_window.isVisible() is True
            assert (
                controller.main_window.stacked_widget.currentWidget()
                == controller.main_window.settings_tab
            )
            mock_warning.assert_called_once()
            args, kwargs = mock_warning.call_args
            assert "Gemini" in args[1]
