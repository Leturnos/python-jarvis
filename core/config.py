import yaml
from core.logger_config import logger

def load_config():
    """Loads application configuration from config.yaml."""
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {
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
