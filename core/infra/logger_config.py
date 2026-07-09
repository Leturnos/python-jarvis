import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(log_dir: str | None = None) -> logging.Logger:
    """Configures the logging system for console and file output with rotation.

    Args:
        log_dir (str | None): Custom directory path for logs. If None, resolves to
            the 'logs' directory under the project root.
    """
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)

    project_root = Path(__file__).parent.parent.parent.absolute()

    # Resolve log directory
    if log_dir is None:
        resolved_log_dir = project_root / "logs"
    else:
        resolved_log_dir = Path(log_dir)

    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = resolved_log_dir / "jarvis.log"

    # Logging levels configuration via env var with default fallback to INFO
    env_level = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, env_level, logging.INFO)

    # Get "Jarvis" logger and isolate it from the root logger
    jarvis_logger = logging.getLogger("Jarvis")
    jarvis_logger.propagate = False
    jarvis_logger.setLevel(log_level)

    # Remove and close existing handlers to avoid duplicates on re-trigger
    for h in jarvis_logger.handlers[:]:
        jarvis_logger.removeHandler(h)
        h.close()

    # Create rotating file handler
    rotating_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    rotating_handler.setFormatter(formatter)

    # Create stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Add handlers
    jarvis_logger.addHandler(rotating_handler)
    jarvis_logger.addHandler(stream_handler)

    # Legacy migration: clean old log file in project root if it exists
    # ONLY perform migration when log_dir is None (production path)
    # Perform this after handlers are ready so we can log warnings directly to Jarvis logger
    if log_dir is None:
        legacy_log_path = project_root / "jarvis.log"
        if legacy_log_path.exists():
            try:
                legacy_log_path.unlink()
            except OSError as e:
                # Log legacy cleanup warnings directly to Jarvis logger
                jarvis_logger.warning(f"Could not remove legacy log: {e}")

    return jarvis_logger


logger = setup_logger()
