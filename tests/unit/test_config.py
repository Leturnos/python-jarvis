from pathlib import Path
from unittest.mock import mock_open, patch

import yaml

from core.infra.config import (
    deep_merge,
    load_config,
    update_yaml_weather_city,
)


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


def test_command_palette_config_defaults():
    with patch("builtins.open", mock_open(read_data="")):
        cfg = load_config()
        assert "command_palette" in cfg
        assert cfg["command_palette"]["key"] == "ctrl+shift+p"


def test_load_config_uses_get_user_config_path():
    with (
        patch(
            "core.infra.config.get_user_config_path",
            return_value=Path("/test/app/root/config.yaml"),
        ) as mock_cfg_path,
        patch("builtins.open", mock_open(read_data="{}")) as mock_file,
    ):
        load_config()
        mock_cfg_path.assert_called()
        mock_file.assert_called_with(
            Path("/test/app/root/config.yaml"), encoding="utf-8"
        )


def test_update_yaml_weather_city(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    initial_yaml = """# Config
tools:
  weather:
    enabled: true
    default_city: "Curitiba"
    timeout_seconds: 5.0
"""
    config_file.write_text(initial_yaml, encoding="utf-8")

    with patch("core.infra.config.get_user_config_path", return_value=config_file):
        update_yaml_weather_city("São Paulo")

    updated = config_file.read_text(encoding="utf-8")
    assert 'default_city: "São Paulo"' in updated
    assert "timeout_seconds: 5.0" in updated

    # Test that surrounding or internal quotes are sanitized and do not corrupt YAML
    with patch("core.infra.config.get_user_config_path", return_value=config_file):
        update_yaml_weather_city('"Rio de Janeiro"')

    updated_quoted = config_file.read_text(encoding="utf-8")
    assert 'default_city: "Rio de Janeiro"' in updated_quoted
    parsed = yaml.safe_load(updated_quoted)
    assert parsed["tools"]["weather"]["default_city"] == "Rio de Janeiro"
