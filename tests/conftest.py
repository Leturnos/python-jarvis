from typing import Any
from unittest.mock import MagicMock

import pytest

from core.runtime.state import JarvisState, state_manager


@pytest.fixture(autouse=True)
def reset_state() -> None:
    """Resets the global state manager state and callbacks to prevent cross-test pollution."""
    state_manager.set_state(JarvisState.IDLE)
    state_manager._callbacks = []


@pytest.fixture
def base_config() -> dict[str, Any]:
    """Default configuration fixture containing typical production keys for tests."""
    return {
        "jarvis": {
            "threshold": 0.5,
            "volume_multiplier": 1.0,
            "cooldown_seconds": 5,
        },
        "voice_activation": {
            "mode": "hybrid",
            "push_to_talk": {
                "key": "ctrl+alt",
                "behavior": "hold",
            },
            "wake_word": {
                "enabled": True,
                "keyword": "hey_jarvis",
            },
            "auto_suspend": {
                "fullscreen": True,
            },
        },
    }


@pytest.fixture
def mock_dispatcher() -> MagicMock:
    """Mock action dispatcher with an embedded tts_engine mock."""
    dispatcher = MagicMock()
    dispatcher.tts_engine = MagicMock()
    return dispatcher


@pytest.fixture
def mock_notifier() -> MagicMock:
    """Mock notifier system to verify notification toast triggers."""
    return MagicMock()


@pytest.fixture
def mock_tts_engine() -> MagicMock:
    """Mock TTS Engine."""
    return MagicMock()
