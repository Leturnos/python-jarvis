from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from core.ui.main_window import MainWindow


def test_main_window_tabs_structure():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)

    assert window.windowTitle() == "Painel do Jarvis"
    assert window.stacked_widget.count() == 4
    assert "status" in window.pivot.items
    assert "history" in window.pivot.items
    assert "plugins" in window.pivot.items
    assert "settings" in window.pivot.items
    assert window.pivot.items["status"].text() == "Status"
    assert window.pivot.items["history"].text() == "Histórico"
    assert window.pivot.items["plugins"].text() == "Plugins"
    assert window.pivot.items["settings"].text() == "Configurações"


def test_history_tab_headers_and_buttons_in_portuguese():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)

    assert window.history_tab.refresh_btn.text() == "Atualizar Histórico"
    headers = [
        window.history_tab.table.horizontalHeaderItem(i).text()
        for i in range(window.history_tab.table.columnCount())
    ]
    assert headers == ["ID", "Horário", "Comando / Pergunta", "Resultado"]


@patch("core.ui.tabs.settings_tab.InfoBar.success")
@patch(
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key",
    return_value=True,
)
def test_settings_tab_validate_key_success(mock_validate, mock_success):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    window.settings_tab.provider_combo.setCurrentIndex(0)
    provider_name = window.settings_tab.providers[0].capitalize()

    window.settings_tab.check_key_btn.click()

    mock_validate.assert_called_once_with(window.settings_tab.providers[0])
    mock_success.assert_called_once_with(
        "Chave de API",
        f"A chave para {provider_name} está configurada.",
        parent=window.settings_tab,
    )


@patch("core.ui.tabs.settings_tab.InfoBar.warning")
@patch(
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key",
    return_value=False,
)
def test_settings_tab_validate_key_missing(mock_validate, mock_warning):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    window.settings_tab.provider_combo.setCurrentIndex(0)
    provider_name = window.settings_tab.providers[0].capitalize()

    window.settings_tab.check_key_btn.click()

    mock_validate.assert_called_once_with(window.settings_tab.providers[0])
    mock_warning.assert_called_once_with(
        "Chave de API",
        f"A chave para {provider_name} não foi configurada.",
        parent=window.settings_tab,
    )


@patch("core.ui.tabs.settings_tab.InfoBar.success")
@patch("core.ui.tabs.settings_tab.KeyringManager.set_secret")
def test_settings_tab_save_key_to_keyring(mock_set_secret, mock_success):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab
    tab.provider_combo.setCurrentIndex(0)
    prov = tab.providers[0]

    tab.api_key_input.setText("test-key-12345")
    tab.save_key_btn.click()

    mock_set_secret.assert_called_once_with(
        "python-jarvis",
        f"{prov.upper()}_API_KEY",
        "test-key-12345",
    )
    assert tab.api_key_input.text() == ""
    mock_success.assert_called_once_with(
        "Chave Salva",
        f"A chave para {prov.capitalize()} foi salva no Keyring com sucesso!",
        parent=tab,
    )


@patch("core.ui.tabs.settings_tab.InfoBar.warning")
@patch("core.ui.tabs.settings_tab.KeyringManager.set_secret")
def test_settings_tab_save_key_empty(mock_set_secret, mock_warning):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab
    tab.api_key_input.setText("   ")
    tab.save_key_btn.click()

    mock_set_secret.assert_not_called()
    mock_warning.assert_called_once_with(
        "Chave Vazia",
        "Por favor, digite ou cole uma chave válida.",
        parent=tab,
    )


@patch("core.ai.llm_agent.llm_agent.reinit_provider")
@patch("core.ui.tabs.settings_tab.InfoBar.success")
@patch("core.ui.tabs.settings_tab.KeyringManager.set_secret")
def test_settings_tab_save_key_reinitializes_active_provider(
    mock_set_secret, mock_success, mock_reinit
):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    import core.ai.llm_agent  # noqa: F401

    mock_set_secret.reset_mock()

    with patch(
        "core.ui.tabs.settings_tab.config",
        {"llm": {"active_provider": "gemini"}},
    ):
        tab.provider_combo.setCurrentIndex(tab.providers.index("gemini"))
        tab.api_key_input.setText("gemini-test-key")
        tab.save_key_btn.click()

        mock_set_secret.assert_called_once_with(
            "python-jarvis",
            "GEMINI_API_KEY",
            "gemini-test-key",
        )
        mock_reinit.assert_called_once()

    # When saving for a different provider, reinit_provider should not be called
    mock_reinit.reset_mock()
    mock_set_secret.reset_mock()
    with patch(
        "core.ui.tabs.settings_tab.config",
        {"llm": {"active_provider": "gemini"}},
    ):
        tab.provider_combo.setCurrentIndex(tab.providers.index("openai"))
        tab.api_key_input.setText("openai-test-key")
        tab.save_key_btn.click()

        mock_set_secret.assert_called_once_with(
            "python-jarvis",
            "OPENAI_API_KEY",
            "openai-test-key",
        )
        mock_reinit.assert_not_called()


@patch("core.ui.tabs.settings_tab.update_yaml_active_provider")
@patch("core.ai.llm_agent.llm_agent.reinit_provider")
@patch("core.ui.tabs.settings_tab.InfoBar.success")
@patch(
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key",
    return_value=True,
)
def test_settings_tab_set_active_provider_success(
    mock_validate, mock_success, mock_reinit, mock_update_yaml
):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab
    tab.provider_combo.setCurrentIndex(tab.providers.index("openai"))

    with patch(
        "core.ui.tabs.settings_tab.config",
        {"llm": {"active_provider": "gemini"}},
    ):
        tab.set_active_btn.click()

        mock_validate.assert_called_once_with("openai")
        mock_update_yaml.assert_called_once_with("openai")
        mock_reinit.assert_called_once()
        mock_success.assert_called_once_with(
            "Provedor Ativo",
            "Provedor alterado para Openai.",
            parent=tab,
        )


def test_settings_tab_update_section_components():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    from core.shared.paths import get_app_version

    assert hasattr(tab, "version_label")
    assert hasattr(tab, "update_status_label")
    assert hasattr(tab, "check_update_btn")
    assert hasattr(tab, "apply_update_btn")
    assert tab.check_update_btn.text() == "Verificar Atualizações"
    assert f"v{get_app_version()}" in tab.version_label.text()


def test_settings_tab_check_update_none():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    from core.infra.updater import ReleaseInfo
    from core.shared.paths import get_app_version

    current_ver = get_app_version()
    info = ReleaseInfo(
        version=f"v{current_ver}",
        title=f"v{current_ver}",
        body="",
        html_url="",
        download_url="",
        asset_name="",
        asset_size=0,
        has_update=False,
    )
    with patch.object(tab.update_mgr, "check_for_updates", return_value=info):
        tab._check_updates_sync()
        assert "versão mais recente" in tab.update_status_label.text()
        assert tab.apply_update_btn.isHidden()


def test_settings_tab_check_update_available():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    from core.infra.updater import ReleaseInfo

    future_ver = "v999.0.0"
    info = ReleaseInfo(
        version=future_ver,
        title=future_ver,
        body="Notas da versão",
        html_url="",
        download_url="https://example.com/asset.zip",
        asset_name="asset.zip",
        asset_size=1024,
        has_update=True,
    )
    with patch.object(tab.update_mgr, "check_for_updates", return_value=info):
        tab._check_updates_sync()
        assert future_ver in tab.update_status_label.text()
        assert not tab.apply_update_btn.isHidden()
        assert future_ver in tab.apply_update_btn.text()


def test_settings_tab_on_download_finished_emits_update_restart_requested(
    tmp_path,
):
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    received_paths = []
    tab.update_restart_requested.connect(lambda path: received_paths.append(path))

    extracted_dir = tmp_path / "extracted_jarvis"
    extracted_dir.mkdir()

    tab._on_download_finished(extracted_dir)

    assert tab.update_status_label.text() == "Aplicando atualização e reiniciando..."
    assert len(received_paths) == 1
    assert received_paths[0] == extracted_dir


def test_settings_tab_on_update_extracting():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    tab._on_update_extracting()
    assert tab.update_status_label.text() == "Extraindo arquivos..."


def test_settings_tab_on_download_finished_non_path_fallback():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    with patch.object(tab, "_on_update_failed") as mock_failed:
        tab._on_download_finished("not-a-path-object")
        mock_failed.assert_called_once_with("Diretório de arquivos extraídos inválido.")


def test_settings_tab_save_weather_city():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    with patch(
        "core.ui.tabs.settings_tab.update_yaml_weather_city"
    ) as mock_update_yaml:
        tab.city_input.setText("São Paulo")
        tab.save_city_btn.click()

        mock_update_yaml.assert_called_once_with("São Paulo")
        from core.infra.config import config

        assert config["tools"]["weather"]["default_city"] == "São Paulo"


def test_settings_tab_open_config_actions_and_labels():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    assert hasattr(tab, "open_config_btn")
    assert hasattr(tab, "open_folder_btn")
    assert tab.open_config_btn.toolTip() == "Abrir config.yaml no editor padrão"
    assert (
        tab.open_folder_btn.toolTip()
        == "Abrir pasta de configuração no Windows Explorer"
    )

    with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open:
        tab.open_config_btn.click()
        assert mock_open.called

    with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open:
        tab.open_folder_btn.click()
        assert mock_open.called


def test_main_window_frameless_and_custom_title_bar():
    from PySide6.QtCore import Qt

    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.width() == 640
    assert window.height() == 500
    assert hasattr(window, "title_bar")
    assert window.title_bar.title_label.text() == "Jarvis"


def test_settings_tab_subtabs_and_mini_monitor_position_sync():
    from PySide6.QtCore import QRect

    from core.ui.screen_position import (
        SCREEN_POSITIONS_ORDER,
        calculate_screen_position,
    )

    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    # Now 3 sub-tabs after merging performance into system
    assert tab.sub_stack.count() == 3
    assert "ui_voice" in tab.sub_pivot.items
    assert "ai_keys" in tab.sub_pivot.items
    assert "sys_upd" in tab.sub_pivot.items
    assert "perf_loc" not in tab.sub_pivot.items

    # Verify switches have fixed width for alignment
    assert tab.audio_cues_switch.width() == 102
    assert tab.fullscreen_suspend_switch.width() == 102
    assert tab.dry_run_switch.width() == 102
    assert tab.autostart_switch.width() == 102

    # Verify MiniMonitorPreview clicking updates combo and config
    with patch("core.ui.tabs.settings_tab.update_yaml_ui_position") as mock_pos_yaml:
        tab.mini_monitor.spot_buttons["bottom_right"].click()
        assert (
            tab.confirmation_pos_combo.currentIndex()
            == SCREEN_POSITIONS_ORDER.index("bottom_right")
        )
        mock_pos_yaml.assert_called_once_with("confirmation_position", "bottom_right")

    # Verify screen position math across spots
    screen_geo = QRect(0, 0, 1920, 1080)
    top_center_pt = calculate_screen_position(screen_geo, 480, 200, "top_center")
    center_pt = calculate_screen_position(screen_geo, 480, 200, "center")
    bottom_center_pt = calculate_screen_position(screen_geo, 480, 200, "bottom_center")

    assert top_center_pt.x() == (1920 - 480) // 2
    assert top_center_pt.y() < center_pt.y() < bottom_center_pt.y()


def test_settings_tab_autostart_sync_methods():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    toggled_records = []
    tab.autostart_toggled.connect(lambda v: toggled_records.append(v))

    with patch("core.ui.tabs.settings_tab.manage_autostart") as mock_manage:
        tab.autostart_switch.setChecked(True)
        assert mock_manage.called

    tab.set_autostart_state(False)
    assert not tab.autostart_switch.isChecked()
    tab.set_autostart_state(True)
    assert tab.autostart_switch.isChecked()


def test_settings_tab_shortcuts_save():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    assert hasattr(tab, "wake_keyword_combo")
    assert hasattr(tab, "wake_keyword_input")
    assert hasattr(tab, "ptt_key_input")
    assert hasattr(tab, "ptt_behavior_combo")
    assert hasattr(tab, "command_palette_key_input")
    assert hasattr(tab, "save_shortcuts_btn")

    # Verify comboboxes have expanded width (190px) to prevent cutting off text
    assert tab.confirmation_pos_combo.maximumWidth() == 190
    assert tab.hud_pos_combo.maximumWidth() == 190

    # Verify space to underscore replacement on wake keyword input
    tab.wake_keyword_input.setText("hey jarvis assistant")
    assert tab.wake_keyword_input.text() == "hey_jarvis_assistant"

    with patch("core.ui.tabs.settings_tab.update_yaml_str_setting") as mock_str_setting:
        tab.wake_keyword_input.setText("hey jarvis")
        tab.ptt_key_input.setText("ctrl+alt")
        tab.ptt_behavior_combo.setCurrentIndex(0)  # hold
        tab.command_palette_key_input.setText("ctrl+shift+p")

        tab.save_shortcuts_btn.click()

        # Should have called update_yaml_str_setting for keyword, key, behavior, and command_palette
        assert mock_str_setting.call_count == 4
        calls = [c.args for c in mock_str_setting.call_args_list]
        assert ("voice_activation", "keyword", "hey_jarvis") in calls
        assert ("voice_activation", "key", "ctrl+alt") in calls
        assert ("voice_activation", "behavior", "hold") in calls
        assert ("command_palette", "key", "ctrl+shift+p") in calls


def test_settings_tab_ai_preferences_save():
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    tab = window.settings_tab

    assert hasattr(tab, "proactivity_combo")
    assert hasattr(tab, "response_phrase_input")
    assert hasattr(tab, "web_search_combo")
    assert hasattr(tab, "city_input")
    assert hasattr(tab, "save_city_btn")

    with (
        patch("core.ui.tabs.settings_tab.update_yaml_str_setting") as mock_str_setting,
        patch(
            "core.ui.tabs.settings_tab.update_yaml_weather_city"
        ) as mock_city_setting,
    ):
        tab.proactivity_combo.setCurrentIndex(1)  # proactive
        tab.response_phrase_input.setText("Às ordens!")
        tab.web_search_combo.setCurrentIndex(0)  # duckduckgo
        tab.city_input.setText("Belo Horizonte")

        tab.save_city_btn.click()

        assert mock_str_setting.call_count == 3
        mock_city_setting.assert_called_once_with("Belo Horizonte")
        calls = [c.args for c in mock_str_setting.call_args_list]
        assert ("ai", "proactivity", "proactive") in calls
        assert ("voice_activation", "response_phrase", "Às ordens!") in calls
        assert ("tools", "provider", "duckduckgo") in calls
