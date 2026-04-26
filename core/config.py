import os
import yaml
import re
from dotenv import load_dotenv
from core.logger_config import logger

load_dotenv()

def expand_env_vars(data):
    """Recursively expand environment variables in a dictionary."""
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(i) for i in data]
    elif isinstance(data, str):
        return os.path.expandvars(data)
    else:
        return data

def load_config():
    """Loads application configuration from config.yaml."""
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config_raw = yaml.safe_load(f)
            config = expand_env_vars(config_raw)
            return config
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {
            'jarvis': {
                'threshold': 0.35,
                'cooldown_seconds': 2.0,
                'volume_multiplier': 1.0,
            },
            'quotas': {
                'llm': {
                    'max_requests_per_day': 100,
                    'max_tokens_per_day': 500000,
                }
            },
            'integrations': {
                'warp': {
                    'path': os.environ.get("WARP_PATH", "")
                }
            },
            'wakewords': {
                'hey_jarvis': {
                    'action': 'warp',
                    'commands': [rf"cd {os.environ.get('PROJECT_PATH', '')}", "gemini"]
                }
            }
        }
config = load_config()
