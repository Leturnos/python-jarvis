from unittest.mock import MagicMock, patch

import psutil
import pytest

from core.execution.automator import WarpAutomator, WindowInfo
from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import ExecutionPlan, ExecutionStep, StepType


@pytest.fixture(scope="function")
def real_dispatcher():
    config = {
        "dry_run": {"enabled": False},
        "timeouts": {
            "process_start": 3.0,
            "window_appear": 5.0,
            "focus": 2.0,
            "focus_retries": 3,
        },
    }
    # Clean up notepad at start just in case
    for p in psutil.process_iter(attrs=["name"]):
        if p.info["name"] and p.info["name"].lower() == "notepad.exe":
            try:
                p.terminate()
            except Exception:
                pass

    automator = WarpAutomator(config)
    # Mock speak to keep tests silent while verifying it is called
    automator.speak = MagicMock()
    dispatcher = ActionDispatcher(config, automator)

    yield dispatcher

    # Cleanup notepad at end
    for p in psutil.process_iter(attrs=["name"]):
        if p.info["name"] and p.info["name"].lower() == "notepad.exe":
            try:
                p.terminate()
            except Exception:
                pass


def test_integration_notepad_open_and_write(real_dispatcher):
    # 1. Dispatch a plan to open Notepad and write text
    steps = [
        ExecutionStep(
            type=StepType.OPEN_APP,
            payload={"target": "notepad.exe", "process_name": "notepad.exe"},
        ),
        ExecutionStep(
            type=StepType.WRITE,
            payload={"text": "Hello from Jarvis timing-hardening integration test!"},
        ),
    ]
    plan = ExecutionPlan(
        intent="test_notepad",
        explanation="Testing notepad stabilization and typing focus safety",
        steps=steps,
    )

    # Run the plan
    success = real_dispatcher.execute_plan(plan)
    assert success is True
    assert real_dispatcher._current_plan_window is not None
    assert real_dispatcher._current_plan_window.executable.lower() == "notepad.exe"

    # Verify the dispatcher successfully finished and announced it silently
    real_dispatcher.automator.speak.assert_called_with("Pronto!")


def test_integration_notepad_focus_loss_prevention(real_dispatcher):
    # 1. Open Notepad
    step_open = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={"target": "notepad.exe", "process_name": "notepad.exe"},
    )
    success = real_dispatcher._execute_step(step_open)
    assert success is True
    assert real_dispatcher._current_plan_window is not None

    # 2. Simulate focus loss by mocking get_foreground_window_info to return a different active window
    different_win = WindowInfo(
        hwnd=999999, pid=999999, executable="chrome.exe", title="Chrome"
    )
    with patch.object(
        real_dispatcher.automator,
        "get_foreground_window_info",
        return_value=different_win,
    ):
        # 3. Attempt to type
        step_write = ExecutionStep(
            type=StepType.WRITE, payload={"text": "This should not be written!"}
        )
        success_write = real_dispatcher._execute_step(step_write)
        assert success_write is False

        # Verify the safety check aborted and announced it silently
        real_dispatcher.automator.speak.assert_called_with(
            "Abortado por segurança. O aplicativo alvo perdeu o foco."
        )
