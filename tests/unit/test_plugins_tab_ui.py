import pytest
from PySide6.QtWidgets import QApplication

from core.ui.tabs.plugins_tab import PluginCard, PluginsTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_plugin_card_creation(qapp):
    mock_plugin_info = {
        "id": "test_plugin",
        "name": "Test Plugin",
        "description": "Test plugin description",
        "category": "Test",
        "version": "1.0.0",
        "is_enabled": True,
        "commands_count": 2,
        "commands": [
            {
                "intent": "test_cmd",
                "description": "Test command",
                "phrases": ["test phrase 1", "test phrase 2"],
                "risk_level": "safe",
            }
        ],
    }

    card = PluginCard(mock_plugin_info)
    assert card.title_label.text() == "Test Plugin"
    assert card.switch.isChecked() is True
    assert card.details_container.isHidden() is True

    # Toggle details
    card._toggle_details()
    assert card.details_container.isHidden() is False
    assert card.toggle_details_btn.text() == "Ocultar Comandos"

    card._toggle_details()
    assert card.details_container.isHidden() is True
    assert card.toggle_details_btn.text() == "Ver Comandos"


def test_plugins_tab_instantiation(qapp):
    tab = PluginsTab()
    assert tab.scroll_area is not None
    assert tab.cards_layout.count() >= 6  # 6 default official plugins


def test_main_window_has_plugins_tab(qapp):
    from unittest.mock import MagicMock

    from core.ui.main_window import MainWindow

    mock_adapter = MagicMock()
    mock_adapter.wakeword_name = "hey_jarvis"
    mock_adapter.visual_state_updated = MagicMock()

    window = MainWindow(mock_adapter)
    assert hasattr(window, "plugins_tab")
    assert window.pivot.items.get("plugins") is not None
