import time
from pathlib import Path

from core.infra.logger_config import logger
from core.shared.paths import get_app_root


def get_first_run_marker_path() -> Path:
    """Returns the path to the first run completion marker file."""
    return get_app_root() / "data" / ".first_run_completed"


def is_first_run() -> bool:
    """Returns True if the application has never been initialized on this installation."""
    return not get_first_run_marker_path().exists()


def mark_first_run_completed() -> None:
    """Marks the first run as completed by creating the marker file."""
    marker = get_first_run_marker_path()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        logger.info("Marked first run as completed.")
    except Exception as e:
        logger.error(f"Failed to record first run marker: {e}")
