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
            'warp_path': r"C:\Users\Leandro\AppData\Local\Programs\Warp\Warp.exe",
            'threshold': 0.4,
            'cooldown_seconds': 5,
            'wakeword_name': 'hey_jarvis',
            'volume_multiplier': 1.0,
            'commands': [r"cd C:\Programacao\MVP", "gemini"]
        }

config = load_config()
