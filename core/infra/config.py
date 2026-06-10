import os
from typing import Any, cast

import yaml
from dotenv import load_dotenv

from core.infra.logger_config import logger

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
            },
            "llm": {
                "active_provider": "gemini",
                "providers": {
                    "gemini": {"model": "gemini-2.5-flash"},
                    "openai": {"model": "gpt-4.1-mini"},
                    "anthropic": {"model": "claude-3-5-haiku-latest"},
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
