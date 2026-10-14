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


def test_app_controller_onboarding_mode():
    app = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()
    tray_adapter = MagicMock()

    with patch("core.ui.app_controller.InfoBar.warning") as mock_warning:
        controller = QtAppController(app, ui_adapter, tray_adapter, onboarding=True)

        assert controller.main_window.isVisible() is True
        assert (
            controller.main_window.pivot.currentRouteKey() == "settings"
            or controller.main_window.pivot.currentItem()
            == controller.main_window.pivot.items["settings"]
        )
        assert (
            controller.main_window.stacked_widget.currentWidget()
            == controller.main_window.settings_tab
        )
        mock_warning.assert_called_once()
        args, kwargs = mock_warning.call_args
        assert args[0] == "Bem-vindo ao Jarvis!"
        assert kwargs["parent"] == controller.main_window.settings_tab


def test_quit_app_hides_tray_icon_first():
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())
    call_order: list[str] = []

    controller.tray_icon.hide = MagicMock(
        side_effect=lambda: call_order.append("tray_hide")
    )
    if controller.stop_event is None:
        controller.stop_event = MagicMock()
    controller.stop_event.set = MagicMock(
        side_effect=lambda: call_order.append("stop_event_set")
    )
    controller.voice_overlay.hide = MagicMock(
        side_effect=lambda: call_order.append("voice_overlay_hide")
    )
    controller.main_window.hide = MagicMock(
        side_effect=lambda: call_order.append("main_window_hide")
    )

    with patch("os._exit") as mock_exit:
        controller.quit_app()
        mock_exit.assert_called_once_with(0)

    assert len(call_order) > 0
    assert call_order[0] == "tray_hide"


def test_boot_update_check_suppressed_when_rate_limited():
    app = QApplication.instance() or QApplication([])
    with patch(
        "core.ui.app_controller.config", {"updates": {"check_on_boot": True}, "llm": {}}
    ):
        with patch("core.ui.app_controller.UpdatePreferenceManager") as mock_pref_cls:
            mock_pref = mock_pref_cls.return_value
            mock_pref.can_check_on_boot.return_value = False

            with patch("core.ui.app_controller.UpdateManager") as mock_upd_cls:
                controller = QtAppController(app, MagicMock(), MagicMock())
                controller._run_boot_update_check()
                mock_upd_cls.return_value.check_for_updates.assert_not_called()


def test_boot_update_check_notifies_user_when_allowed():
    app = QApplication.instance() or QApplication([])
    from core.infra.updater import ReleaseInfo

    info = ReleaseInfo(
        version="v999.0.0",
        title="v999.0.0",
        body="Notas",
        html_url="",
        download_url="https://example.com/asset.zip",
        asset_name="asset.zip",
        asset_size=1024,
        has_update=True,
    )

    with patch(
        "core.ui.app_controller.config", {"updates": {"check_on_boot": True}, "llm": {}}
    ):
        with patch("core.ui.app_controller.UpdatePreferenceManager") as mock_pref_cls:
            mock_pref = mock_pref_cls.return_value
            mock_pref.can_check_on_boot.return_value = True
            mock_pref.should_notify_version.return_value = True

            with patch("core.ui.app_controller.UpdateManager") as mock_upd_cls:
                mock_upd_cls.return_value.check_for_updates.return_value = info
                controller = QtAppController(app, MagicMock(), MagicMock())
                controller._show_update_notification = MagicMock()
                controller._run_boot_update_check()
                controller._show_update_notification.assert_called_once_with(info)


def test_app_controller_applies_update_and_quits(tmp_path):
    app = QApplication.instance() or QApplication([])
    controller = QtAppController(app, MagicMock(), MagicMock())

    extracted_dir = tmp_path / "extracted_update"
    extracted_dir.mkdir()

    with patch(
        "core.infra.updater.UpdateManager.apply_update_and_restart"
    ) as mock_apply:
        controller.apply_update_and_restart(extracted_dir)
        mock_apply.assert_called_once_with(
            source_dir=extracted_dir,
            exit_callback=controller.quit_app,
        )
