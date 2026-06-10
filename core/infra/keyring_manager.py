import keyring

from core.infra.logger_config import logger


class KeyringManager:
    @staticmethod
    def get_secret(service: str, username: str) -> str | None:
        """Retrieves a secret from the OS keyring."""
        try:
            return keyring.get_password(service, username)
        except Exception as e:
            logger.error(f"Error retrieving secret from keyring: {e}")
            return None

    @staticmethod
    def set_secret(service: str, username: str, secret: str) -> None:
        """Saves a secret to the OS keyring."""
        try:
            keyring.set_password(service, username, secret)
        except Exception as e:
            logger.error(f"Error saving secret to keyring: {e}")

    @staticmethod
    def delete_secret(service: str, username: str) -> None:
        """Removes a secret from the OS keyring."""
        try:
            keyring.delete_password(service, username)
        except keyring.errors.PasswordDeleteError:
            pass  # Ignore if it doesn't exist
        except Exception as e:
            logger.error(f"Error deleting secret from keyring: {e}")

    @staticmethod
    def validate_provider_key(provider_name: str) -> bool:
        """Validates if the API key for the given provider is available.

        Returns True if found, False otherwise with a friendly log message.
        """
        from dotenv import load_dotenv

        load_dotenv()

        key_name = f"{provider_name.upper()}_API_KEY"
        keyring_key = KeyringManager.get_secret("python-jarvis", key_name)

        import os

        env_key = os.getenv(key_name)

        # Update Keyring if .env key is different or new
        if env_key and (not keyring_key or env_key != keyring_key):
            logger.info(f"Migrating/updating {key_name} from .env to secure Keyring.")
            KeyringManager.set_secret("python-jarvis", key_name, env_key)
            key = env_key
        else:
            key = keyring_key if keyring_key else env_key

        if not key:
            logger.error(
                f"⚠️  API KEY MISSING: The API key for provider '{provider_name}' ({key_name}) was not found."
            )
            logger.info(
                f"💡 FIX: Add '{key_name}=your_key' to your .env file and restart Jarvis."
            )
            return False

        return True

    @staticmethod
    def check_capability(provider_name: str, capability: str) -> bool:
        """Checks if a provider has a specific capability."""
        # This can be expanded later
        capabilities = {
            "gemini": ["json_mode", "system_instructions"],
            "openai": ["json_mode", "system_instructions", "tool_use"],
            "anthropic": ["system_instructions", "tool_use"],
            "deepseek": ["json_mode", "system_instructions"],
            "openrouter": ["json_mode", "system_instructions"],
        }
        return capability in capabilities.get(provider_name.lower(), [])
