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
    assert "Paleta de Comandos" in controller.palette_action.text()

    # Verify _update_menu_states dynamically updates the hotkey label
    with patch(
        "core.ui.app_controller.config",
        {"command_palette": {"key": "ctrl+alt+k"}, "llm": {}},
    ):
        controller._update_menu_states()
        assert "Paleta de Comandos (Ctrl+Alt+K)..." == controller.palette_action.text()

    controller.palette_action.trigger()
    controller.command_palette.show.assert_called_once()


def test_tray_menu_actions_and_labels_in_portuguese():
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())

    # Check primary actions
    assert controller.show_action.text() == "Exibir Painel"
    assert "Paleta de Comandos" in controller.palette_action.text()
    assert controller.active_action.text() == "Ouvindo (Ativo)"
    assert controller.suspended_action.text() == "Em Espera (Pausado)"
    assert controller.autostart_action.text() == "Iniciar com o Windows"

    # Check quit action
    quit_actions = [a for a in controller.tray_menu.actions() if a.text() == "Sair"]
    assert len(quit_actions) == 1

    # Check mute submenu and options
    assert controller.mute_menu.title() == "Silenciar por..."
    assert controller.mute_30m.text() == "30 minutos"
    assert controller.mute_1h.text() == "1 hora"
    assert controller.mute_3h.text() == "3 horas"

    # Check provider submenu
    assert controller.provider_menu.title() == "Provedor de IA"


def test_switch_provider_missing_key_notification_in_portuguese():
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())
    controller.tray_adapter.mute_until = 0.0
    controller.tray_icon.showMessage = MagicMock()

    with patch(
        "core.ui.app_controller.KeyringManager.validate_provider_key",
        return_value=False,
    ):
        controller._switch_provider("openai")

    controller.tray_icon.showMessage.assert_called_once()
    args, _ = controller.tray_icon.showMessage.call_args
    assert args[0] == "Jarvis"
    assert args[1] == "Chave de API do Openai não configurada."


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
