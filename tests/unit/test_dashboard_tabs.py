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
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key", return_value=True
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
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key", return_value=False
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
        "core.ui.tabs.settings_tab.config", {"llm": {"active_provider": "gemini"}}
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
        "core.ui.tabs.settings_tab.config", {"llm": {"active_provider": "gemini"}}
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
    "core.ui.tabs.settings_tab.KeyringManager.validate_provider_key", return_value=True
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
        "core.ui.tabs.settings_tab.config", {"llm": {"active_provider": "gemini"}}
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
