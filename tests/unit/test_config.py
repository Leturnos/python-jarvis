from unittest.mock import mock_open, patch

import yaml

from core.infra.config import deep_merge, load_config


def test_deep_merge():
    base = {
        "stt": {"model_size": "tiny", "language": "pt"},
        "timing": {"delay": 0.5},
    }
    override = {"stt": {"model_size": "base"}, "custom": "value"}
    result = deep_merge(base, override)
    assert result["stt"]["model_size"] == "base"
    assert result["stt"]["language"] == "pt"
    assert result["timing"]["delay"] == 0.5
    assert result["custom"] == "value"


def test_load_config_with_preset():
    yaml_content = yaml.dump(
        {
            "performance_profile": "ultra_economic",
            "stt": {"language": "en"},  # Override language
        }
    )
    with patch("builtins.open", mock_open(read_data=yaml_content)):
        cfg = load_config()
        assert cfg["performance_profile"] == "ultra_economic"
        assert cfg["stt"]["model_size"] == "tiny"
        assert cfg["stt"]["auto_unload_seconds"] == 30
        assert cfg["stt"]["language"] == "en"  # Overridden!


def test_load_config_auto_preset():
    yaml_content = yaml.dump({"performance_profile": "auto"})
    with (
        patch("builtins.open", mock_open(read_data=yaml_content)),
        patch(
            "core.infra.config.detect_recommended_preset",
            return_value="performance",
        ),
    ):
        cfg = load_config()
        assert cfg["performance_profile"] == "auto"
        assert cfg["_resolved_profile"] == "performance"
        assert cfg["stt"]["model_size"] == "base"
        assert cfg["stt"]["auto_unload_seconds"] == 0
