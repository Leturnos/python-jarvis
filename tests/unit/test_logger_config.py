import logging
import os
from logging.handlers import RotatingFileHandler

import pytest

from core.infra.logger_config import setup_logger


@pytest.fixture(autouse=True)
def restore_production_logger():
    """Teardown fixture that restores the 'Jarvis' logger state to production configurations

    to prevent other tests running in the same pytest process from facing closed/orphaned file handles.
    """
    yield
    setup_logger()  # restores setup targeting production paths


def test_setup_logger_uses_rotating_file_handler(tmp_path):
    # Act
    jarvis_logger = setup_logger(log_dir=str(tmp_path))

    # Find the RotatingFileHandler in the "Jarvis" logger handlers
    rotating_handlers = [
        h for h in jarvis_logger.handlers if isinstance(h, RotatingFileHandler)
    ]

    assert len(rotating_handlers) == 1, (
        "RotatingFileHandler not found in 'Jarvis' logger handlers"
    )

    handler = rotating_handlers[0]
    normalized_path = os.path.normpath(handler.baseFilename)

    # Assert configurations
    assert os.path.dirname(normalized_path) == str(tmp_path)
    assert os.path.basename(normalized_path) == "jarvis.log"
    assert handler.maxBytes == 5_000_000
    assert handler.backupCount == 3
    assert handler.encoding == "utf-8"


def test_setup_logger_default_level_is_info(tmp_path):
    # Remove env var if set
    original_env = os.environ.get("JARVIS_LOG_LEVEL")
    if "JARVIS_LOG_LEVEL" in os.environ:
        del os.environ["JARVIS_LOG_LEVEL"]

    try:
        jarvis_logger = setup_logger(log_dir=str(tmp_path))
        assert jarvis_logger.level == logging.INFO
    finally:
        if original_env is not None:
            os.environ["JARVIS_LOG_LEVEL"] = original_env


def test_setup_logger_honors_env_level_override(tmp_path):
    # Force override to DEBUG
    original_env = os.environ.get("JARVIS_LOG_LEVEL")
    os.environ["JARVIS_LOG_LEVEL"] = "DEBUG"

    try:
        jarvis_logger = setup_logger(log_dir=str(tmp_path))
        assert jarvis_logger.level == logging.DEBUG
    finally:
        if original_env is not None:
            os.environ["JARVIS_LOG_LEVEL"] = original_env
        else:
            del os.environ["JARVIS_LOG_LEVEL"]


def test_rotation_actually_occurs(tmp_path):
    # Setup custom small RotatingFileHandler on a separate test logger
    log_file = tmp_path / "rotation_test.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=100, backupCount=2, encoding="utf-8"
    )

    logger = logging.getLogger("rotation_test_logger")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    # Write enough lines to exceed 100 bytes
    for _ in range(10):
        logger.debug("x" * 20)

    # Clean up handlers to release file locks on Windows
    logger.removeHandler(handler)
    handler.close()

    # Assert that rotation occurred and backup file exists
    assert os.path.exists(str(log_file))
    assert os.path.exists(str(tmp_path / "rotation_test.log.1"))
