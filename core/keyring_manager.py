import keyring
from core.logger_config import logger

class KeyringManager:
    @staticmethod
    def get_secret(service: str, username: str) -> str:
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
            pass # Ignore if it doesn't exist
        except Exception as e:
            logger.error(f"Error deleting secret from keyring: {e}")
