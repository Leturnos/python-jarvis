from plyer import notification

from core.infra.logger_config import logger


class JarvisNotifier:
    def __init__(self) -> None:
        pass

    def notify(self, title: str, message: str, duration: int = 3) -> None:
        """Sends a native Windows notification using Plyer."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Jarvis",
                timeout=duration,
                # ticker='Jarvis Notification' # for Android/other OS
            )
        except Exception as e:
            logger.error(f"Failed to show notification via Plyer: {e}")
