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
            "tts": {"provider": "sapi5", "voice_keyword": "maria"},
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
                }
            },
            "integrations": {"warp": {"path": os.environ.get("WARP_PATH", "")}},
            "wakewords": {
                "hey_jarvis": {
                    "action": "warp",
                    "commands": [rf"cd {os.environ.get('PROJECT_PATH', '')}", "gemini"],
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
