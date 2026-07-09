import logging
import threading
from unittest.mock import MagicMock

import pytest

from core.runtime.state import JarvisState, StateManager


def test_state_initialization() -> None:
    """Verifies that a new StateManager starts in IDLE and has an empty context."""
    manager = StateManager()
    assert manager.get_state() == JarvisState.IDLE
    assert manager.get_context() == {}


def test_get_state_and_context() -> None:
    """Verifies retrieval of state and context copy."""
    manager = StateManager()
    manager.set_state(JarvisState.LISTENING, {"key": "value"})

    assert manager.get_state() == JarvisState.LISTENING
    ctx = manager.get_context()
    assert ctx == {"key": "value"}

    # Verify copy is defensive (modifying copy shouldn't change internal dict)
    ctx["key"] = "hacked"
    assert manager.get_context() == {"key": "value"}


def test_state_transitions_valid() -> None:
    """Verifies valid transitions update state and context."""
    manager = StateManager()

    # IDLE -> LISTENING (valid)
    manager.set_state(JarvisState.LISTENING, {"session": "123"})
    assert manager.get_state() == JarvisState.LISTENING
    assert manager.get_context() == {"session": "123"}

    # LISTENING -> THINKING (valid)
    manager.set_state(JarvisState.THINKING, {"query": "test"})
    assert manager.get_state() == JarvisState.THINKING
    assert manager.get_context() == {"query": "test"}

    # THINKING -> EXECUTING (valid)
    manager.set_state(JarvisState.EXECUTING)
    assert manager.get_state() == JarvisState.EXECUTING
    assert manager.get_context() == {}


def test_state_transitions_invalid_logs_warning_but_proceeds() -> None:
    """Verifies that an invalid transition logs a warning but is still allowed to prevent locking."""
    manager = StateManager()
    # Transition: IDLE -> COOLDOWN (not defined in allowed_transitions)
    manager.set_state(JarvisState.COOLDOWN, {"reason": "test"})

    assert manager.get_state() == JarvisState.COOLDOWN
    assert manager.get_context() == {"reason": "test"}


def test_transition_to_same_state() -> None:
    """Verifies that transitioning to the same state updates or keeps context."""
    manager = StateManager()
    manager.set_state(JarvisState.LISTENING, {"first": 1})

    # Re-transition to same state with new context update
    manager.set_state(JarvisState.LISTENING, {"second": 2})
    assert manager.get_state() == JarvisState.LISTENING
    assert manager.get_context() == {"first": 1, "second": 2}

    # Re-transition to same state with context=None (should keep current context)
    manager.set_state(JarvisState.LISTENING, None)
    assert manager.get_context() == {"first": 1, "second": 2}


def test_callbacks_notification() -> None:
    """Verifies that registered callbacks are notified on transition."""
    manager = StateManager()
    callback1 = MagicMock()
    callback2 = MagicMock()

    manager.add_callback(callback1)
    manager.add_callback(callback2)

    manager.set_state(JarvisState.LISTENING, {"foo": "bar"})

    callback1.assert_called_once_with(
        JarvisState.IDLE, JarvisState.LISTENING, {"foo": "bar"}
    )
    callback2.assert_called_once_with(
        JarvisState.IDLE, JarvisState.LISTENING, {"foo": "bar"}
    )


def test_callback_exception_handling(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an exception in a callback doesn't prevent other callbacks from executing."""
    manager = StateManager()

    bad_callback = MagicMock(side_effect=Exception("Failed callback"))
    good_callback = MagicMock()

    manager.add_callback(bad_callback)
    manager.add_callback(good_callback)

    # Enable propagation temporarily for the test so caplog can intercept it
    jarvis_logger = logging.getLogger("Jarvis")
    original_propagate = jarvis_logger.propagate
    jarvis_logger.propagate = True
    caplog.set_level("ERROR", logger="Jarvis")

    try:
        # Trigger transition
        manager.set_state(JarvisState.MUTED)

        # Both should have been called
        bad_callback.assert_called_once()
        good_callback.assert_called_once()

        # Warning/error should be logged
        assert any(
            "Error in state callback" in record.message for record in caplog.records
        )
    finally:
        jarvis_logger.propagate = original_propagate


def test_state_thread_safety() -> None:
    """Simulates concurrent state updates to ensure thread safety."""
    manager = StateManager()
    errors = []

    def worker_func(idx: int) -> None:
        try:
            # Alternate states to cause changes
            state = JarvisState.LISTENING if idx % 2 == 0 else JarvisState.THINKING
            manager.set_state(state, {f"thread_{idx}": True})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker_func, args=(i,)) for i in range(10)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert manager.get_state() in (JarvisState.LISTENING, JarvisState.THINKING)
