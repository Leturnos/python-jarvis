import copy
import os
from typing import Any, cast

import yaml
from dotenv import load_dotenv

from core.infra.logger_config import logger
from core.infra.presets import PRESETS, detect_recommended_preset
from core.shared.constants import DEFAULT_MODELS, DEFAULT_PROVIDER

load_dotenv()


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
    try:
        with open("config.yaml", encoding="utf-8") as f:
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
                "fuzzy_match_threshold": 0.7,
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
