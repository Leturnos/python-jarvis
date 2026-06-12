import time
from typing import Any
from unittest.mock import MagicMock, patch

from core.activation import (
    ActivationActionType,
    ActivationContext,
    ActivationManager,
)
from core.runtime.state import JarvisState


def test_activation_manager_init(base_config: dict[str, Any]) -> None:
    """Verifies fields are correctly initialized from config."""
    am = ActivationManager(base_config)
    assert am.mode == "hybrid"
    assert am.ptt_key == "ctrl+alt"
    assert am.ptt_behavior == "hold"
    assert am.auto_suspend is True
    assert am.is_ptt_active is False
    assert am.metrics["activation_wake_word"] == 0


def test_evaluate_none_action(base_config: dict[str, Any]) -> None:
    """Verifies that NONE action is returned when no activation conditions are met."""
    am = ActivationManager(base_config)
    context = ActivationContext(
        wakeword_score=0.1,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=time.time(),
    )
    action = am.evaluate(context)
    assert action.action_type == ActivationActionType.NONE
    assert action.source == "NONE"


def test_evaluate_fullscreen_suspend(base_config: dict[str, Any]) -> None:
    """Verifies that fullscreen suspends the assistant when in IDLE."""
    am = ActivationManager(base_config)
    timestamp = 100.0
    context = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=True,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=timestamp,
    )
    action = am.evaluate(context)
    assert action.action_type == ActivationActionType.SUSPEND
    assert action.source == "FULLSCREEN_APP"
    assert am.last_state_change_time == timestamp
    assert am.metrics["activation_suspend"] == 1
    assert am.metrics["fullscreen_suspend_count"] == 1


def test_evaluate_fullscreen_resume_with_hysteresis(
    base_config: dict[str, Any],
) -> None:
    """Verifies resume is blocked by hysteresis and allowed after MIN_SUSPEND_DURATION."""
    am = ActivationManager(base_config)
    am.last_state_change_time = 100.0

    # Context suspended, still fullscreen (remain suspended)
    context1 = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=True,
        is_hotkey_pressed=False,
        current_state=JarvisState.SUSPENDED,
        timestamp=101.0,  # 1s after change
    )
    action1 = am.evaluate(context1)
    assert action1.action_type == ActivationActionType.NONE

    # Context suspended, NOT fullscreen but WITHIN hysteresis (remain suspended)
    context2 = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.SUSPENDED,
        timestamp=101.5,  # 1.5s after change (MIN_SUSPEND_DURATION is 2.0)
    )
    action2 = am.evaluate(context2)
    assert action2.action_type == ActivationActionType.NONE

    # Context suspended, NOT fullscreen, OUTSIDE hysteresis (resume allowed)
    context3 = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.SUSPENDED,
        timestamp=103.0,  # 3s after change (exceeds 2.0s)
    )
    action3 = am.evaluate(context3)
    assert action3.action_type == ActivationActionType.RESUME
    assert action3.source == "FULLSCREEN_APP"
    assert am.metrics["activation_resume"] == 1
    assert am.last_state_change_time == 103.0


def test_evaluate_push_to_talk(base_config: dict[str, Any]) -> None:
    """Verifies hybrid PTT starts and stops activation."""
    am = ActivationManager(base_config)

    # PTT starts
    context_press = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=True,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
    )
    action = am.evaluate(context_press)
    assert action.action_type == ActivationActionType.TRIGGER_PTT_START
    assert action.source == "PTT"
    assert am.is_ptt_active is True
    assert am.metrics["activation_ptt"] == 1

    # PTT held (returns NONE, already active)
    action_held = am.evaluate(context_press)
    assert action_held.action_type == ActivationActionType.NONE

    # PTT released
    context_release = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=101.0,
    )
    action_stop = am.evaluate(context_release)
    assert action_stop.action_type == ActivationActionType.TRIGGER_PTT_STOP
    assert action_stop.source == "PTT"
    assert am.is_ptt_active is False


def test_evaluate_wakeword_trigger(base_config: dict[str, Any]) -> None:
    """Verifies Wake Word activates Jarvis when keyword matches and score is above threshold."""
    am = ActivationManager(base_config)

    # Below threshold score
    context_low = ActivationContext(
        wakeword_score=0.4,  # Config threshold is 0.5
        wakeword_detected="hey_jarvis",
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
    )
    assert am.evaluate(context_low).action_type == ActivationActionType.NONE

    # Wrong keyword
    context_wrong = ActivationContext(
        wakeword_score=0.8,
        wakeword_detected="hey_alexa",
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
    )
    assert am.evaluate(context_wrong).action_type == ActivationActionType.NONE

    # Trigger success
    context_ok = ActivationContext(
        wakeword_score=0.8,
        wakeword_detected="hey_jarvis",
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=100.0,
    )
    action = am.evaluate(context_ok)
    assert action.action_type == ActivationActionType.TRIGGER_WAKE
    assert action.source == "WAKE_WORD"
    assert am.metrics["activation_wake_word"] == 1


@patch("core.activation.win32gui")
@patch("core.activation.win32api")
def test_is_fullscreen_true(
    mock_win32api: MagicMock, mock_win32gui: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fullscreen is detected when window covers the whole screen."""
    am = ActivationManager(base_config)

    # Active window
    mock_win32gui.GetForegroundWindow.return_value = 12345
    # Not desktop
    mock_win32gui.GetClassName.return_value = "NotDesktopClass"
    # Matches screen size
    mock_win32gui.GetWindowRect.return_value = (0, 0, 1920, 1080)
    mock_win32api.GetSystemMetrics.side_effect = lambda metric: (
        1920 if metric == 0 else 1080
    )

    assert am.is_fullscreen() is True


@patch("core.activation.win32gui")
@patch("core.activation.win32api")
def test_is_fullscreen_false_small_window(
    mock_win32api: MagicMock, mock_win32gui: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fullscreen is False if window is smaller than screen."""
    am = ActivationManager(base_config)

    mock_win32gui.GetForegroundWindow.return_value = 12345
    mock_win32gui.GetClassName.return_value = "Chrome_WidgetWin_1"
    mock_win32gui.GetWindowRect.return_value = (100, 100, 800, 600)
    mock_win32api.GetSystemMetrics.side_effect = lambda metric: (
        1920 if metric == 0 else 1080
    )

    assert am.is_fullscreen() is False


@patch("core.activation.win32gui")
def test_is_fullscreen_no_active_window(
    mock_win32gui: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fullscreen is False if there is no active window."""
    am = ActivationManager(base_config)
    mock_win32gui.GetForegroundWindow.return_value = 0
    assert am.is_fullscreen() is False


@patch("core.activation.win32gui")
def test_is_fullscreen_desktop_classes(
    mock_win32gui: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fullscreen is False on desktop classes (Progman, WorkerW, Shell_TrayWnd)."""
    am = ActivationManager(base_config)
    mock_win32gui.GetForegroundWindow.return_value = 12345

    for cls in ("Progman", "WorkerW", "Shell_TrayWnd"):
        mock_win32gui.GetClassName.return_value = cls
        assert am.is_fullscreen() is False


@patch("core.activation.win32gui")
def test_is_fullscreen_exception(
    mock_win32gui: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies exceptions in win32 calls return False and are handled safely."""
    am = ActivationManager(base_config)
    mock_win32gui.GetForegroundWindow.side_effect = Exception("OS Crash")
    assert am.is_fullscreen() is False


@patch("core.activation.win32api")
def test_is_hotkey_pressed_modifier_keys(
    mock_win32api: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies hotkey detection for virtual modifiers (ctrl+alt)."""
    am = ActivationManager(base_config)

    # Mock ctrl (VK_CONTROL = 17) and alt (VK_MENU = 18) as pressed (MSB set, e.g. 0x8000)
    mock_win32api.GetAsyncKeyState.side_effect = lambda vk: (
        0x8000 if vk in (17, 18) else 0
    )

    assert am.is_hotkey_pressed() is True

    # Mock ctrl pressed, but alt released
    mock_win32api.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == 17 else 0
    assert am.is_hotkey_pressed() is False


@patch("core.activation.win32api")
def test_is_hotkey_pressed_chars(
    mock_win32api: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies hotkey detection for normal character combinations (e.g. shift+a)."""
    config = {
        "voice_activation": {
            "push_to_talk": {
                "key": "shift+a",
            }
        }
    }
    am = ActivationManager(config)

    # VK_SHIFT = 16, ord('A') = 65
    mock_win32api.GetAsyncKeyState.side_effect = lambda vk: (
        0x8000 if vk in (16, 65) else 0
    )
    assert am.is_hotkey_pressed() is True

    mock_win32api.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == 16 else 0
    assert am.is_hotkey_pressed() is False


@patch("core.activation.win32api")
@patch("core.activation.keyboard")
def test_is_hotkey_pressed_fallback_keyboard(
    mock_keyboard: MagicMock, mock_win32api: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fallback to keyboard module for complex named keys or other situations."""
    config = {
        "voice_activation": {
            "push_to_talk": {
                "key": "f12",
            }
        }
    }
    am = ActivationManager(config)

    # GetAsyncKeyState returns 0 (not pressed or unmapped)
    mock_win32api.GetAsyncKeyState.return_value = 0
    mock_keyboard.is_pressed.return_value = True

    assert am.is_hotkey_pressed() is True
    mock_keyboard.is_pressed.assert_called_with("f12")


@patch("core.activation.win32api")
@patch("core.activation.keyboard")
def test_is_hotkey_pressed_fallback_keyboard_false(
    mock_keyboard: MagicMock, mock_win32api: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies fallback to keyboard module returns False when key is not pressed."""
    config = {
        "voice_activation": {
            "push_to_talk": {
                "key": "f12",
            }
        }
    }
    am = ActivationManager(config)

    mock_win32api.GetAsyncKeyState.return_value = 0
    mock_keyboard.is_pressed.return_value = False

    assert am.is_hotkey_pressed() is False


@patch("core.activation.win32api")
@patch("core.activation.keyboard")
def test_is_hotkey_pressed_exception_handling(
    mock_keyboard: MagicMock, mock_win32api: MagicMock, base_config: dict[str, Any]
) -> None:
    """Verifies exceptions in hotkey check fail gracefully to keyboard logical check, then False."""
    am = ActivationManager(base_config)

    mock_win32api.GetAsyncKeyState.side_effect = Exception("VKey API Error")
    mock_keyboard.is_pressed.side_effect = Exception("Keyboard Error")

    # Should not crash, just return False
    assert am.is_hotkey_pressed() is False
