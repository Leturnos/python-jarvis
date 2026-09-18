from unittest.mock import MagicMock, patch

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


def test_tray_menu_has_command_palette_action():
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())
    controller.tray_adapter.mute_until = 0.0
    controller.command_palette = MagicMock()

    assert hasattr(controller, "palette_action")
    assert "Command Palette" in controller.palette_action.text()

    # Verify _update_menu_states dynamically updates the hotkey label
    with patch(
        "core.ui.app_controller.config",
        {"command_palette": {"key": "ctrl+alt+k"}, "llm": {}},
    ):
        controller._update_menu_states()
        assert "Command Palette (Ctrl+Alt+K)..." == controller.palette_action.text()

    controller.palette_action.trigger()
    controller.command_palette.show.assert_called_once()


def test_start_command_palette_uses_configured_hotkey():
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())
    with patch("keyboard.add_hotkey") as mock_add_hotkey:
        with patch(
            "core.ui.app_controller.config",
            {"command_palette": {"key": "ctrl+shift+space"}},
        ):
            controller.start_command_palette(MagicMock())
            mock_add_hotkey.assert_called_once_with(
                "ctrl+shift+space", controller.command_palette.show
            )
