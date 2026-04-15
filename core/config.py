import os
import yaml
from core.logger_config import logger

def load_config():
    """Loads application configuration from config.yaml."""
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            # Allow environment variable to override YAML
            env_key = os.getenv("GEMINI_API_KEY")
            if env_key:
                config["gemini_api_key"] = env_key
            return config
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {
            'gemini_api_key': os.getenv("GEMINI_API_KEY", ""),
            'threshold': 0.35,
            'cooldown_seconds': 2.0,
            'volume_multiplier': 1.0,
            'wakewords': {
                'hey_jarvis': {
                    'action_type': 'warp',
                    'warp_path': r"C:\Users\Leandro\AppData\Local\Programs\Warp\Warp.exe",
                    'commands': [r"cd C:\Programacao\MVP", "gemini"]
                }
            }
        }

config = load_config()
