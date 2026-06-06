from unittest.mock import MagicMock

import pytest

from core.execution.automator import WindowInfo
from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import ExecutionStep, StepType


@pytest.fixture
def dispatcher():
    config = {
        "dry_run": {"enabled": False},
        "timeouts": {
            "process_start": 1.0,
            "window_appear": 1.0,
            "focus": 1.0,
            "focus_retries": 2,
        },
    }
    automator = MagicMock()
    # Mock speak to prevent actual speaking or errors
    automator.speak = MagicMock()
    return ActionDispatcher(config, automator)


def test_dispatcher_open_app_stores_window(dispatcher):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    dispatcher.automator.open_and_stabilize_app.return_value = target_win

    step = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={
            "target": "notepad.exe",
            "window_title_pattern": "notepad",
            "process_name": "notepad.exe",
        },
    )

    success = dispatcher._execute_step(step)
    assert success is True
    assert dispatcher._current_plan_window == target_win
    assert dispatcher._current_plan_window_pattern == "notepad"
    dispatcher.automator.open_and_stabilize_app.assert_called_once_with(
        target="notepad.exe", window_title_pattern="notepad", process_name="notepad.exe"
    )


def test_dispatcher_typing_allowed_when_focus_correct(dispatcher):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    dispatcher._current_plan_window = target_win
    dispatcher._current_plan_window_pattern = "Test"

    dispatcher.automator.get_foreground_window_info.return_value = target_win
    dispatcher.automator.check_focus_match.return_value = True

    step = ExecutionStep(type=StepType.WRITE, payload={"text": "hello"})

    success = dispatcher._execute_step(step)
    assert success is True
    dispatcher.automator.type_text.assert_called_once_with("hello")


def test_dispatcher_typing_aborts_when_focus_lost(dispatcher):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    active_win = WindowInfo(hwnd=202, pid=604, executable="chrome.exe", title="Google")

    dispatcher._current_plan_window = target_win
    dispatcher._current_plan_window_pattern = "Test"

    dispatcher.automator.get_foreground_window_info.return_value = active_win
    dispatcher.automator.check_focus_match.return_value = False

    step = ExecutionStep(type=StepType.WRITE, payload={"text": "hello"})

    success = dispatcher._execute_step(step)
    assert success is False
    # type_text should NOT be called since focus was lost
    dispatcher.automator.type_text.assert_not_called()
    dispatcher.automator.speak.assert_called_once_with(
        "Abortado por segurança. O aplicativo alvo perdeu o foco."
    )
