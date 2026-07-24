import os
from typing import Any, cast

import yaml
from dotenv import load_dotenv

from core.infra.logger_config import logger
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


def load_config() -> dict[str, Any]:
    """Loads application configuration from config.yaml."""
    try:
        with open("config.yaml", encoding="utf-8") as f:
            config_raw = yaml.safe_load(f)
            config = cast(dict[str, Any], expand_env_vars(config_raw))
            return config
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {
            "jarvis": {
                "threshold": 0.35,
                "cooldown_seconds": 2.0,
                "volume_multiplier": 1.0,
            },
            "voice_activation": {
                "mode": "hybrid",
                "push_to_talk": {"key": "ctrl+alt", "behavior": "hold"},
                "wake_word": {"enabled": True, "keyword": "hey jarvis"},
                "auto_suspend": {"fullscreen": True},
                "thresholds": {
                    "silence_rms": 15.0,
                    "speech_rms": 20.0,
                    "max_zero_rms_frames": 30,
                },
                "timeouts": {
                    "silence_end_seconds": 1.5,
                    "max_listening_seconds": 10.0,
                },
                "device_index": None,
                "frames_per_buffer": 1280,
            },
            "stt": {
                "model_size": "tiny",
                "language": "pt",
                "device": "cpu",
                "compute_type": "int8",
            },
            "llm": {
                "active_provider": DEFAULT_PROVIDER,
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
            "timing": {
                "ui_stabilization_short": 0.1,
                "ui_stabilization_medium": 0.3,
                "ui_stabilization_long": 0.5,
                "warp_startup_delay": 2.0,
                "warp_tab_creation": 1.2,
                "warp_cmd_execution": 0.6,
                "window_search_sleep": 0.2,
                "window_recovery_sleep": 0.4,
                "post_focus_render_sleep": 0.5,
                "autoplay_click_delay": 1.8,
                "mouse_detect_polling": 0.1,
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
            "runtime": {
                "memory_monitor": {
                    "interval_seconds": 60,
                    "threshold_mb": 800.0,
                }
            },
        }


config = load_config()


def reload_config() -> dict[str, Any]:
    """Reloads the configuration from config.yaml and updates the global config dict."""
    global config
    new_config = load_config()
    config.clear()
    config.update(new_config)
    return config
