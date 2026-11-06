import json
import threading
import time
from pathlib import Path
from typing import Any

from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.paths import get_user_data_dir


class UpdatePreferenceManager:
    """Manages update suppression preferences, notification cooldowns, and boot-check rate limits."""

    def __init__(
        self,
        state_file: Path | str | None = None,
        check_interval_hours: float | None = None,
        notification_cooldown_hours: float | None = None,
    ) -> None:
        if state_file is None:
            self.state_file = get_user_data_dir() / "updates_state.json"
        else:
            self.state_file = Path(state_file)

        update_cfg = config.get("updates", {})
        if check_interval_hours is not None:
            self.check_interval_hours = float(check_interval_hours)
        else:
            # Read from config with fallback to 2h
            self.check_interval_hours = float(
                update_cfg.get("check_interval_hours", 2.0)
            )

        if notification_cooldown_hours is not None:
            self.notification_cooldown_hours = float(notification_cooldown_hours)
        else:
            # Read from config with fallback to 24h
            self.notification_cooldown_hours = float(
                update_cfg.get("notification_cooldown_hours", 24.0)
            )

        self._lock = threading.Lock()
        self.last_check_timestamp: float = 0.0
        self.last_notified_timestamp: float = 0.0
        self.last_notified_version: str | None = None
        self.dismissed_until: float = 0.0
        self.dismissed_version: str | None = None

        self._load()

    def _load(self) -> None:
        """Loads state from disk safely, recovering defaults on error."""
        with self._lock:
            if not self.state_file.exists():
                return
            try:
                data: dict[str, Any] = json.loads(
                    self.state_file.read_text(encoding="utf-8")
                )
                self.last_check_timestamp = float(data.get("last_check_timestamp", 0.0))
                self.last_notified_timestamp = float(
                    data.get("last_notified_timestamp", 0.0)
                )
                self.last_notified_version = data.get("last_notified_version")
                self.dismissed_until = float(data.get("dismissed_until", 0.0))
                self.dismissed_version = data.get("dismissed_version")
            except Exception as e:
                logger.warning(
                    f"Failed to parse update state from {self.state_file}: {e}. Resetting to defaults."
                )
                self.last_check_timestamp = 0.0
                self.last_notified_timestamp = 0.0
                self.last_notified_version = None
                self.dismissed_until = 0.0
                self.dismissed_version = None

    def _save(self) -> None:
        """Writes current state to disk atomically."""
        with self._lock:
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "last_check_timestamp": self.last_check_timestamp,
                    "last_notified_timestamp": self.last_notified_timestamp,
                    "last_notified_version": self.last_notified_version,
                    "dismissed_until": self.dismissed_until,
                    "dismissed_version": self.dismissed_version,
                }
                temp_file = self.state_file.with_suffix(".tmp")
                temp_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                temp_file.replace(self.state_file)
            except Exception as e:
                logger.error(f"Failed to persist update preferences: {e}")

    def can_check_on_boot(self, now: float | None = None) -> bool:
        """Returns True if enough time has passed since the last background boot check."""
        self._load()
        current_time = time.time() if now is None else now
        with self._lock:
            elapsed_seconds = current_time - self.last_check_timestamp
            required_interval_seconds = self.check_interval_hours * 3600.0
            return elapsed_seconds >= required_interval_seconds

    def should_notify_version(self, version: str, now: float | None = None) -> bool:
        """Returns True if a notification for this specific version is allowed.

        Returns False if:
        1. The user explicitly chose to ignore/skip this exact version.
        2. The user requested 'Not now' (snooze) and the snooze period has not elapsed yet.
        3. A notification for this exact version was already displayed within the cooldown window.
        """
        self._load()
        current_time = time.time() if now is None else now
        with self._lock:
            if self.dismissed_version and self.dismissed_version == version:
                return False
            if current_time < self.dismissed_until:
                return False
            if self.last_notified_version == version and (
                current_time - self.last_notified_timestamp
            ) < (self.notification_cooldown_hours * 3600.0):
                return False
            return True

    def record_check(self, timestamp: float | None = None) -> None:
        """Records that an update check just completed."""
        self._load()
        current_time = time.time() if timestamp is None else timestamp
        with self._lock:
            self.last_check_timestamp = current_time
        self._save()

    def record_notification(self, version: str, timestamp: float | None = None) -> None:
        """Records that a notification was shown for a specific version."""
        self._load()
        current_time = time.time() if timestamp is None else timestamp
        with self._lock:
            self.last_notified_timestamp = current_time
            self.last_notified_version = version
        self._save()

    def snooze(self, hours: float = 24.0, now: float | None = None) -> None:
        """Snoozes update popups/notifications for the given number of hours."""
        self._load()
        current_time = time.time() if now is None else now
        with self._lock:
            self.dismissed_until = current_time + (hours * 3600.0)
        self._save()

    def dismiss_version(self, version: str) -> None:
        """Permanently skips notifications for this specific version until a newer version is released."""
        self._load()
        with self._lock:
            self.dismissed_version = version
        self._save()

    def reset_dismissed_version(self) -> None:
        """Resets dismissed version to allow future notifications."""
        self._load()
        with self._lock:
            self.dismissed_version = None
        self._save()
