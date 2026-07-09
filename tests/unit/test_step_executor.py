from unittest.mock import MagicMock, patch

from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.step_executor import StepExecutor
from core.execution.window_manager import WindowInfo


def test_step_executor_wait():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    step = ExecutionStep(type=StepType.WAIT, payload={"duration": 0.01})
    assert executor.execute_step(step) is True


@patch("subprocess.run")
def test_step_executor_command_safe_split(mock_run):
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    command_str = 'git commit -m "feat: test"'
    step = ExecutionStep(type=StepType.COMMAND, payload={"command": command_str})

    success = executor.execute_step(step)
    assert success is True
    mock_run.assert_called_once_with(
        ["git", "commit", "-m", "feat: test"], shell=False, check=True
    )


@patch("subprocess.run")
def test_step_executor_command_builtin_allowed(mock_run):
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    command_str = 'echo "hello world"'
    step = ExecutionStep(type=StepType.COMMAND, payload={"command": command_str})

    success = executor.execute_step(step)
    assert success is True
    mock_run.assert_called_once_with(
        ["cmd", "/c", 'echo "hello world"'], shell=False, check=True
    )


def test_step_executor_command_builtin_injection_blocked():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    # Builtin with command concatenation attempted (parentheses and ampersand)
    command_str = "echo (hello) & calc.exe"
    step = ExecutionStep(type=StepType.COMMAND, payload={"command": command_str})

    success = executor.execute_step(step)
    assert success is False
    tts.speak.assert_called_once_with(
        "Comando bloqueado por conter caracteres especiais perigosos."
    )


def test_step_executor_command_empty_fails():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    step = ExecutionStep(type=StepType.COMMAND, payload={"command": "   "})

    success = executor.execute_step(step)
    assert success is False


@patch("subprocess.run")
def test_step_executor_command_nonexistent_executable_fails_gracefully(mock_run):
    mock_run.side_effect = FileNotFoundError(
        "[WinError 2] O sistema nao pode encontrar o arquivo especificado"
    )
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    step = ExecutionStep(
        type=StepType.COMMAND,
        payload={"command": "nonexistent_system_app_123.exe --arg"},
    )

    success = executor.execute_step(step)
    assert success is False
    tts.speak.assert_called_once_with(
        "O sistema não conseguiu encontrar o executável especificado."
    )


def test_step_executor_navigate_types_when_focused():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    executor._current_plan_window = target_win
    executor._current_plan_window_pattern = "Test"

    wm.get_foreground_window_info.return_value = target_win
    wm.check_focus_match.return_value = True

    target_path = r"C:\Programacao\python-jarvis"
    step = ExecutionStep(type=StepType.NAVIGATE, payload={"target": target_path})

    with patch("pyautogui.press") as mock_press:
        success = executor.execute_step(step)
        assert success is True
        wm.type_text.assert_called_once_with(f"cd /d {target_path}")
        mock_press.assert_called_once_with("enter")


def test_step_executor_navigate_aborts_when_focus_lost():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    active_win = WindowInfo(hwnd=202, pid=604, executable="chrome.exe", title="Google")

    executor._current_plan_window = target_win
    executor._current_plan_window_pattern = "Test"

    wm.get_foreground_window_info.return_value = active_win
    wm.check_focus_match.return_value = False

    target_path = r"C:\Programacao\python-jarvis"
    step = ExecutionStep(type=StepType.NAVIGATE, payload={"target": target_path})

    success = executor.execute_step(step)
    assert success is False
    wm.type_text.assert_not_called()
    tts.speak.assert_called_once_with(
        "Abortado por segurança. O aplicativo alvo perdeu o foco."
    )
