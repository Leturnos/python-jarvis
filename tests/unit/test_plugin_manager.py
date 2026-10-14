import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from core.infra.config import update_yaml_plugin_preset
from core.plugins.plugin_manager import PluginManager


@pytest.fixture
def temp_plugins_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create sample plugin 1
        p1 = {
            "id": "sample_system",
            "name": "Sample System",
            "description": "System shortcuts",
            "category": "Sistema",
            "version": "1.0.0",
            "commands": [
                {
                    "intent": "open_calc",
                    "description": "Opens Calculator",
                    "phrases": ["open calculator", "calc"],
                    "risk_level": "safe",
                    "actions": [{"type": "system_open", "target": "calc:"}],
                }
            ],
        }
        with open(tmp_path / "sample_system.yaml", "w", encoding="utf-8") as f:
            yaml.dump(p1, f)

        # Create sample plugin 2
        p2 = {
            "id": "sample_dev",
            "name": "Sample Dev",
            "description": "Dev automations",
            "category": "Dev",
            "version": "1.0.0",
            "commands": [
                {
                    "intent": "run_tests",
                    "description": "Runs test suite",
                    "phrases": ["run tests", "pytest"],
                    "risk_level": "safe",
                    "actions": [{"type": "type_and_enter", "text": "pytest"}],
                }
            ],
        }
        with open(tmp_path / "sample_dev.yaml", "w", encoding="utf-8") as f:
            yaml.dump(p2, f)

        yield tmp_path


def test_plugin_discovery_and_metadata(temp_plugins_dir):
    with patch(
        "core.plugins.plugin_manager.config",
        {"plugins": {"enabled_presets": ["sample_system", "sample_dev"]}},
    ):
        pm = PluginManager(plugins_dir=temp_plugins_dir)
        available = pm.get_available_plugins()
        assert len(available) == 2

        ids = {p["id"] for p in available}
        assert ids == {"sample_system", "sample_dev"}

        intents = pm.get_intents()
        intent_names = {i["intent"] for i in intents}
        assert intent_names == {"open_calc", "run_tests"}


def test_plugin_toggle_disabled(temp_plugins_dir):
    mock_config = {"plugins": {"enabled_presets": ["sample_system", "sample_dev"]}}
    with (
        patch("core.plugins.plugin_manager.config", mock_config),
        patch(
            "core.plugins.plugin_manager.update_yaml_plugin_preset"
        ) as mock_update_yaml,
    ):
        pm = PluginManager(plugins_dir=temp_plugins_dir)
        assert pm.is_plugin_enabled("sample_dev") is True

        listener = MagicMock()
        pm.register_change_listener(listener)

        # Disable sample_dev
        pm.set_plugin_enabled("sample_dev", False)

        mock_update_yaml.assert_called_with("sample_dev", False)
        listener.assert_called_once()
        assert pm.is_plugin_enabled("sample_dev") is False

        # Only sample_system intents should remain
        active_intents = [i["intent"] for i in pm.get_intents()]
        assert "open_calc" in active_intents
        assert "run_tests" not in active_intents

        # Actions for disabled intent should return None
        assert pm.get_actions_for_intent("run_tests") is None
        assert pm.get_actions_for_intent("open_calc") is not None


def test_plugin_toggle_re_enable(temp_plugins_dir):
    mock_config = {"plugins": {"enabled_presets": ["sample_system"]}}
    with (
        patch("core.plugins.plugin_manager.config", mock_config),
        patch("core.plugins.plugin_manager.update_yaml_plugin_preset"),
    ):
        pm = PluginManager(plugins_dir=temp_plugins_dir)
        assert pm.is_plugin_enabled("sample_dev") is False
        assert "run_tests" not in [i["intent"] for i in pm.get_intents()]

        # Re-enable sample_dev
        pm.set_plugin_enabled("sample_dev", True)
        assert pm.is_plugin_enabled("sample_dev") is True

        active_intents = [i["intent"] for i in pm.get_intents()]
        assert "run_tests" in active_intents
        assert pm.get_actions_for_intent("run_tests") == [
            {"type": "type_and_enter", "text": "pytest"}
        ]


def test_update_yaml_plugin_preset(tmp_path):
    config_file = tmp_path / "config.yaml"
    initial_content = {
        "llm": {"active_provider": "gemini"},
        "plugins": {"enabled_presets": ["devtools", "windows_system"]},
    }
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(initial_content, f)

    with patch("core.infra.config.get_app_root", return_value=tmp_path):
        # Disable windows_system
        update_yaml_plugin_preset("windows_system", False)
        with open(config_file, encoding="utf-8") as f:
            updated = yaml.safe_load(f)
        assert "windows_system" not in updated["plugins"]["enabled_presets"]
        assert "devtools" in updated["plugins"]["enabled_presets"]

        # Re-enable windows_system
        update_yaml_plugin_preset("windows_system", True)
        with open(config_file, encoding="utf-8") as f:
            updated_again = yaml.safe_load(f)
        assert "windows_system" in updated_again["plugins"]["enabled_presets"]


def test_official_presets_loaded_in_project():
    from core.plugins.plugin_manager import plugin_manager

    available = plugin_manager.get_available_plugins()
    available_ids = {p["id"] for p in available}

    expected = {
        "devtools",
        "windows_system",
        "web_browsing",
        "productivity",
        "media_entertainment",
        "gaming",
    }
    assert expected.issubset(available_ids)

    # Check that commands are loaded and have phrases
    intents = plugin_manager.get_intents()
    assert len(intents) >= 20

    intent_map = {i["intent"]: i for i in intents}
    assert "bloquear_computador" in intent_map
    assert intent_map["bloquear_computador"]["risk_level"] == "dangerous"
    assert "fechar_tudo" not in intent_map
    assert "abrir_youtube" in intent_map
    assert "mutar_som" in intent_map
    assert "abrir_steam" in intent_map
    assert "programar" in intent_map
