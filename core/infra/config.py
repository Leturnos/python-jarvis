import copy
import os
from typing import Any, cast

import yaml
from dotenv import load_dotenv

from core.infra.logger_config import logger
from core.infra.presets import PRESETS, detect_recommended_preset
from core.shared.constants import DEFAULT_MODELS, DEFAULT_PROVIDER
from core.shared.paths import get_app_root

load_dotenv(get_app_root() / ".env")


def expand_env_vars(data: Any) -> Any:
    """Recursively expand environment variables in a dictionary."""
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(i) for i in data]
    elif isinstance(data, str):
        return os.path.expandvars(data)
    else:
        return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries, giving priority to override values."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config() -> dict[str, Any]:
    """Loads application configuration, applying performance presets and config.yaml overrides."""
    yaml_path = get_app_root() / "config.yaml"
    try:
        with open(yaml_path, encoding="utf-8") as f:
            config_raw = yaml.safe_load(f) or {}
            user_config = cast(dict[str, Any], expand_env_vars(config_raw))
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        user_config = {}

    profile_setting = user_config.get("performance_profile", "auto")
    if profile_setting == "auto" or profile_setting not in PRESETS:
        resolved_profile = detect_recommended_preset()
    else:
        resolved_profile = profile_setting

    preset_base = copy.deepcopy(PRESETS.get(resolved_profile, PRESETS["balanced"]))

    common_defaults = {
        "paths": {
            "data_dir": "data",
            "models_dir": "models",
        },
        "jarvis": {
            "threshold": 0.35,
            "cooldown_seconds": 2.0,
            "volume_multiplier": 1.0,
        },
        "voice_activation": {
            "mode": "hybrid",
            "volume_multiplier": 1.0,
            "cooldown_seconds": 2.5,
            "response_phrase": "Sim?",
            "push_to_talk": {"key": "ctrl+alt", "behavior": "hold"},
            "wake_word": {"enabled": True, "keyword": "hey_jarvis", "threshold": 0.5},
            "auto_suspend": {"fullscreen": True},
            "thresholds": {
                "silence_rms": 15.0,
                "speech_rms": 20.0,
                "max_zero_rms_frames": 500,
            },
            "timeouts": {
                "silence_end_seconds": 1.5,
                "max_listening_seconds": 10.0,
            },
            "device_index": None,
            "frames_per_buffer": 1280,
        },
        "command_palette": {
            "key": "ctrl+shift+p",
        },
        "llm": {
            "active_provider": DEFAULT_PROVIDER,
            "timeout_seconds": 5.0,
            "num_retries": 0,
            "providers": {
                "gemini": {"model": DEFAULT_MODELS["gemini"]},
                "openai": {"model": DEFAULT_MODELS["openai"]},
                "anthropic": {"model": DEFAULT_MODELS["anthropic"]},
                "deepseek": {"model": DEFAULT_MODELS["deepseek"]},
                "openrouter": {"model": DEFAULT_MODELS["openrouter"]},
            },
        },
        "tts": {
            "provider": "sapi5",
            "voice_keyword": "maria",
            "rate": 2,
            "volume": 100,
            "cooldown_seconds": 2.0,
        },
        "dry_run": {
            "enabled": True,
            "bypass_for_safe_intents": True,
            "timeout_seconds": 15,
        },
        "timeouts": {
            "process_start": 5.0,
            "window_appear": 10.0,
            "focus": 3.0,
            "focus_retries": 3,
        },
        "quotas": {
            "llm": {
                "max_requests_per_day": 100,
                "max_tokens_per_day": 500000,
            }
        },
        "ai": {
            "nlp": {
                "fuzzy_match_threshold": 0.75,
            }
        },
        "automation": {
            "cv": {
                "template_confidence_high": 0.7,
                "template_confidence_low": 0.4,
            },
            "spotify": {
                "green_hsv_lower": [55, 100, 100],
                "green_hsv_upper": [85, 255, 255],
                "header_offset": 120,
                "search_vertical_offset_ratio": 0.1,
                "search_x_ratio": 0.25,
                "search_y_ratio": 0.35,
                "playlist_play_y_ratio": 0.4,
            },
        },
        "integrations": {"warp": {"path": os.environ.get("WARP_PATH", "")}},
        "wakewords": {
            "hey_jarvis": {
                "action": "warp",
                "commands": [rf"cd {os.environ.get('PROJECT_PATH', '')}", "gemini"],
            }
        },
        "audio_cues": {
            "enabled": True,
            "debounce_ms": 200,
            "frequencies": {
                "wake": [800, 80],
                "command_recognized": [1000, 60],
                "action_completed": [1200, 100],
            },
        },
        "plugins": {
            "enabled_presets": [
                "devtools",
                "windows_system",
                "web_browsing",
                "productivity",
                "media_entertainment",
                "gaming",
            ]
        },
    }

    base_config = deep_merge(common_defaults, preset_base)
    final_config = deep_merge(base_config, user_config)
    final_config["_resolved_profile"] = resolved_profile
    return final_config


config = load_config()


def reload_config() -> dict[str, Any]:
    """Reloads the configuration from config.yaml and updates the global config dict."""
    global config
    new_config = load_config()
    config.clear()
    config.update(new_config)
    return config


def update_yaml_active_provider(provider_name: str) -> None:
    """Updates the active_provider entry in config.yaml while preserving file structure."""
    yaml_path = get_app_root() / "config.yaml"
    if not yaml_path.exists():
        return
    with open(yaml_path, encoding="utf-8") as f:
        lines = f.readlines()

    in_llm_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("llm:"):
            in_llm_block = True
        elif in_llm_block and stripped.startswith("active_provider:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f'{indent}active_provider: "{provider_name}"\n'
            break
        elif in_llm_block and (
            line.strip() and not line.startswith(" ") and not line.startswith("\t")
        ):
            in_llm_block = False

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def update_yaml_performance_profile(profile_name: str) -> None:
    """Updates the performance_profile entry in config.yaml while preserving comments and structure."""
    yaml_path = get_app_root() / "config.yaml"
    if not yaml_path.exists():
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(f'performance_profile: "{profile_name}"\n')
        return

    with open(yaml_path, encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith("performance_profile:")
            and not line.startswith(" ")
            and not line.startswith("\t")
        ):
            lines[i] = f'performance_profile: "{profile_name}"\n'
            updated = True
            break

    if not updated:
        lines.insert(0, f'performance_profile: "{profile_name}"\n')

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def update_yaml_plugin_preset(preset_id: str, enabled: bool) -> None:
    """Updates the enabled_presets entry in config.yaml while preserving comments and structure."""
    yaml_path = get_app_root() / "config.yaml"
    if not yaml_path.exists():
        return
    try:
        with open(yaml_path, encoding="utf-8") as f:
            lines = f.readlines()

        in_plugins_block = False
        in_enabled_presets_block = False
        preset_line_idx = -1
        presets_start_idx = -1
        last_item_idx = -1
        indent_str = "    - "

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("plugins:"):
                in_plugins_block = True
                continue
            elif in_plugins_block and (
                stripped
                and not line.startswith(" ")
                and not line.startswith("\t")
                and not stripped.startswith("#")
            ):
                in_plugins_block = False
                in_enabled_presets_block = False

            if in_plugins_block:
                if stripped.startswith("enabled_presets:"):
                    in_enabled_presets_block = True
                    presets_start_idx = i
                    rest = stripped[len("enabled_presets:") :].strip()
                    if rest.startswith("[") and rest.endswith("]"):
                        items = [
                            x.strip().strip("'\"")
                            for x in rest[1:-1].split(",")
                            if x.strip()
                        ]
                        if enabled and preset_id not in items:
                            items.append(preset_id)
                        elif not enabled and preset_id in items:
                            items.remove(preset_id)
                        indent = line[: len(line) - len(line.lstrip())]
                        lines[i] = (
                            f"{indent}enabled_presets: [{', '.join(repr(x) for x in items)}]\n"
                        )
                        with open(yaml_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)
                        return
                    continue
                elif in_enabled_presets_block:
                    if stripped.startswith("-"):
                        last_item_idx = i
                        indent_str = line[: line.index("-") + 2]
                        val = stripped.lstrip("-").strip().strip('"').strip("'")
                        if val == preset_id:
                            preset_line_idx = i
                    elif stripped and not stripped.startswith("#"):
                        in_enabled_presets_block = False

        if not enabled and preset_line_idx != -1:
            lines.pop(preset_line_idx)
        elif enabled and preset_line_idx == -1:
            if not indent_str.endswith(" "):
                indent_str += " "
            new_line = f'{indent_str}"{preset_id}"\n'
            if last_item_idx != -1:
                if not lines[last_item_idx].endswith("\n"):
                    lines[last_item_idx] += "\n"
                lines.insert(last_item_idx + 1, new_line)
            elif presets_start_idx != -1:
                if not lines[presets_start_idx].endswith("\n"):
                    lines[presets_start_idx] += "\n"
                lines.insert(presets_start_idx + 1, new_line)
            else:
                lines.append("\nplugins:\n  enabled_presets:\n")
                lines.append(new_line)

        with open(yaml_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        logger.error(
            f"Failed to update plugin preset '{preset_id}' in config.yaml: {e}"
        )
