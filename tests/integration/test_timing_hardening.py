from unittest.mock import MagicMock, patch

import psutil
import pytest

from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import ExecutionPlan, ExecutionStep, StepType
from core.execution.plan_builder import PlanBuilder
from core.execution.step_executor import StepExecutor
from core.execution.window_manager import WindowInfo, WindowManager
from core.media.cv_matcher import TemplateMatcher
from core.media.spotify_automator import SpotifyAutomator


@pytest.fixture(scope="function", autouse=True)
def mock_os_calls():
    # Mock processes
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 12345, "name": "notepad.exe"}
    mock_proc.name.return_value = "notepad.exe"
    mock_proc.pid = 12345

    # Mock window
    mock_win = MagicMock()
    mock_win._hWnd = 999
    mock_win.hwnd = 999
    mock_win.title = "Untitled - Notepad"
    mock_win.left = 100
    mock_win.top = 100
    mock_win.width = 800
    mock_win.height = 600

    def enum_windows_side_effect(callback, extra):
        callback(999, extra)

    with (
        patch("subprocess.Popen"),
        patch("os.startfile"),
        patch("pyautogui.click"),
        patch("pyautogui.hotkey"),
        patch("pyautogui.press"),
        patch("pyautogui.moveTo"),
        patch("pyperclip.copy"),
        patch("psutil.process_iter", return_value=[mock_proc]),
        patch("psutil.Process", return_value=mock_proc),
        patch("pygetwindow.getAllWindows", return_value=[mock_win]),
        patch("win32gui.EnumWindows", side_effect=enum_windows_side_effect),
        patch("win32gui.GetForegroundWindow", return_value=999),
        patch("win32gui.GetWindowText", return_value="Untitled - Notepad"),
        patch("win32gui.GetWindowRect", return_value=(100, 100, 900, 700)),
        patch("win32gui.IsIconic", return_value=False),
        patch("win32gui.ShowWindow"),
        patch("win32gui.IsWindowVisible", return_value=True),
        patch("win32process.GetWindowThreadProcessId", return_value=(0, 12345)),
        patch("win32gui.SetForegroundWindow"),
    ):
        yield


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

    window_manager = WindowManager()
    tts_engine = MagicMock()
    cv_matcher = TemplateMatcher()
    spotify_automator = SpotifyAutomator(config, window_manager, tts_engine, cv_matcher)
    step_executor = StepExecutor(config, window_manager, spotify_automator, tts_engine)
    plan_builder = PlanBuilder(config)

    dispatcher = ActionDispatcher(config, step_executor, tts_engine, plan_builder)

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
    assert real_dispatcher.step_executor._current_plan_window is not None
    assert (
        real_dispatcher.step_executor._current_plan_window.executable.lower()
        == "notepad.exe"
    )

    # Verify the dispatcher successfully finished and announced it silently
    real_dispatcher.tts_engine.speak.assert_called_with("Pronto!")


def test_integration_notepad_focus_loss_prevention(real_dispatcher):
    # 1. Open Notepad
    step_open = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={"target": "notepad.exe", "process_name": "notepad.exe"},
    )
    success = real_dispatcher.step_executor.execute_step(step_open)
    assert success is True
    assert real_dispatcher.step_executor._current_plan_window is not None

    # 2. Simulate focus loss by mocking get_foreground_window_info to return a different active window
    different_win = WindowInfo(
        hwnd=999999, pid=999999, executable="chrome.exe", title="Chrome"
    )
    with patch.object(
        real_dispatcher.step_executor.window_manager,
        "get_foreground_window_info",
        return_value=different_win,
    ):
        # 3. Attempt to type
        step_write = ExecutionStep(
            type=StepType.WRITE, payload={"text": "This should not be written!"}
        )
        success_write = real_dispatcher.step_executor.execute_step(step_write)
        assert success_write is False

        # Verify the safety check aborted and announced it silently
        real_dispatcher.tts_engine.speak.assert_called_with(
            "Abortado por segurança. O aplicativo alvo perdeu o foco."
        )
