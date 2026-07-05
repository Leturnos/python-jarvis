from unittest.mock import MagicMock

import pytest

from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.step_executor import StepExecutor
from core.execution.window_manager import WindowInfo


@pytest.fixture
def executor():
    config = {
        "dry_run": {"enabled": False},
        "timeouts": {
            "process_start": 1.0,
            "window_appear": 1.0,
            "focus": 1.0,
            "focus_retries": 2,
        },
    }
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    return StepExecutor(config, wm, spotify, tts)


def test_executor_open_app_stores_window(executor):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    executor.window_manager.open_and_stabilize_app.return_value = target_win

    step = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={
            "target": "notepad.exe",
            "window_title_pattern": "notepad",
            "process_name": "notepad.exe",
        },
    )

    success = executor.execute_step(step)
    assert success is True
    assert executor._current_plan_window == target_win
    assert executor._current_plan_window_pattern == "notepad"
    executor.window_manager.open_and_stabilize_app.assert_called_once_with(
        target="notepad.exe",
        window_title_pattern="notepad",
        process_name="notepad.exe",
        timeouts=executor.config.get("timeouts"),
    )


def test_executor_typing_allowed_when_focus_correct(executor):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    executor._current_plan_window = target_win
    executor._current_plan_window_pattern = "Test"

    executor.window_manager.get_foreground_window_info.return_value = target_win
    executor.window_manager.check_focus_match.return_value = True

    step = ExecutionStep(type=StepType.WRITE, payload={"text": "hello"})

    success = executor.execute_step(step)
    assert success is True
    executor.window_manager.type_text.assert_called_once_with("hello")


def test_executor_typing_aborts_when_focus_lost(executor):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    active_win = WindowInfo(hwnd=202, pid=604, executable="chrome.exe", title="Google")

    executor._current_plan_window = target_win
    executor._current_plan_window_pattern = "Test"

    executor.window_manager.get_foreground_window_info.return_value = active_win
    executor.window_manager.check_focus_match.return_value = False

    step = ExecutionStep(type=StepType.WRITE, payload={"text": "hello"})

    success = executor.execute_step(step)
    assert success is False
    # type_text should NOT be called since focus was lost
    executor.window_manager.type_text.assert_not_called()
    executor.tts_engine.speak.assert_called_once_with(
        "Abortado por segurança. O aplicativo alvo perdeu o foco."
    )
