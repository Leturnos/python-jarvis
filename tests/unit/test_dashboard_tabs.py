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
    assert window.stacked_widget.count() == 3
    assert "status" in window.pivot.items
    assert "history" in window.pivot.items
    assert "settings" in window.pivot.items
    assert window.pivot.items["status"].text() == "Status"
    assert window.pivot.items["history"].text() == "Histórico"
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
