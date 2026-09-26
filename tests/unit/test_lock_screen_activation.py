from typing import Any
from unittest.mock import MagicMock, patch

from core.activation import (
    ActivationActionType,
    ActivationContext,
    ActivationManager,
    is_screen_locked,
)
from core.runtime.state import JarvisState


def test_evaluate_lock_screen_suspends_when_idle(base_config: dict[str, Any]) -> None:
    am = ActivationManager(base_config)
    timestamp = 100.0
    context = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=timestamp,
        is_screen_locked=True,
    )
    action = am.evaluate(context)
    assert action.action_type == ActivationActionType.SUSPEND
    assert action.source == "LOCK_SCREEN"
    assert am.metrics["activation_suspend"] == 1
    assert am.metrics["lock_screen_suspend_count"] == 1


def test_evaluate_lock_screen_blocks_wakeword_and_ptt(
    base_config: dict[str, Any],
) -> None:
    am = ActivationManager(base_config)
    context = ActivationContext(
        wakeword_score=0.99,
        wakeword_detected="hey_jarvis",
        is_fullscreen=False,
        is_hotkey_pressed=True,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
        is_screen_locked=True,
    )
    action = am.evaluate(context)
    # Must suspend or return NONE, NEVER trigger wake word or PTT
    assert action.action_type not in (
        ActivationActionType.TRIGGER_WAKE,
        ActivationActionType.TRIGGER_PTT_START,
    )


def test_evaluate_lock_screen_blocks_resume_while_locked(
    base_config: dict[str, Any],
) -> None:
    am = ActivationManager(base_config)
    am.last_state_change_time = 100.0

    context = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.SUSPENDED,
        timestamp=105.0,  # Exceeds hysteresis
        is_screen_locked=True,
    )
    action = am.evaluate(context)
    assert action.action_type == ActivationActionType.NONE


def test_evaluate_lock_screen_resumes_after_unlock(
    base_config: dict[str, Any],
) -> None:
    am = ActivationManager(base_config)
    # 1. Suspend via lock screen
    context_lock = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
        is_screen_locked=True,
    )
    suspend_action = am.evaluate(context_lock)
    assert suspend_action.action_type == ActivationActionType.SUSPEND
    assert suspend_action.source == "LOCK_SCREEN"

    # 2. Resume after unlocking
    context_unlock = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.SUSPENDED,
        timestamp=105.0,  # Exceeds hysteresis
        is_screen_locked=False,
    )
    action = am.evaluate(context_unlock)
    assert action.action_type == ActivationActionType.RESUME
    assert action.source == "LOCK_SCREEN"


@patch("ctypes.windll.user32.OpenInputDesktop")
@patch("ctypes.windll.user32.CloseDesktop")
@patch("ctypes.windll.user32.SwitchDesktop")
def test_is_screen_locked_detection(
    mock_switch: MagicMock, mock_close: MagicMock, mock_open: MagicMock
) -> None:
    # 1. OpenInputDesktop fails (desk == 0) -> locked (secure desktop)
    mock_open.return_value = 0
    assert is_screen_locked() is True

    # 2. OpenInputDesktop succeeds, but SwitchDesktop fails -> locked
    mock_open.return_value = 1234
    mock_switch.return_value = 0
    assert is_screen_locked() is True
    mock_close.assert_called_with(1234)

    # 3. OpenInputDesktop succeeds and SwitchDesktop succeeds -> unlocked
    mock_switch.return_value = 1
    assert is_screen_locked() is False
