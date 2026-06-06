from unittest.mock import MagicMock, patch

import pytest

from core.execution.automator import WarpAutomator, WindowInfo


@pytest.fixture
def automator():
    config = {
        "timeouts": {
            "process_start": 1.0,
            "window_appear": 1.0,
            "focus": 1.0,
            "focus_retries": 2,
        }
    }
    with patch("core.execution.automator.threading.Thread"):
        return WarpAutomator(config)


def test_window_info_dataclass():
    win = WindowInfo(hwnd=123, pid=456, executable="test.exe", title="Test Window")
    assert win.hwnd == 123
    assert win.pid == 456
    assert win.executable == "test.exe"
    assert win.title == "Test Window"


@patch("psutil.process_iter")
def test_find_processes(mock_process_iter, automator):
    mock_p1 = MagicMock()
    mock_p1.info = {
        "pid": 100,
        "name": "notepad.exe",
        "exe": "C:\\Windows\\notepad.exe",
    }

    mock_p2 = MagicMock()
    mock_p2.info = {
        "pid": 200,
        "name": "chrome.exe",
        "exe": "C:\\Program Files\\chrome.exe",
    }

    mock_process_iter.return_value = [mock_p1, mock_p2]

    # Find by name
    pids = automator.find_processes(executable_name="notepad.exe")
    assert pids == {100}

    # Find by path (case-insensitive and normalized)
    pids = automator.find_processes(executable_path="c:/windows/notepad.exe")
    assert pids == {100}

    # Find when none match
    pids = automator.find_processes(executable_name="nonexistent.exe")
    assert pids == set()


@patch("win32gui.GetForegroundWindow")
@patch("win32process.GetWindowThreadProcessId")
@patch("win32gui.GetWindowText")
@patch("psutil.Process")
def test_get_foreground_window_info(
    mock_process_cls,
    mock_get_window_text,
    mock_get_window_pid,
    mock_get_foreground,
    automator,
):
    mock_get_foreground.return_value = 777
    mock_get_window_pid.return_value = (None, 888)
    mock_get_window_text.return_value = "My Active Window"

    mock_proc = MagicMock()
    mock_proc.name.return_value = "active.exe"
    mock_process_cls.return_value = mock_proc

    info = automator.get_foreground_window_info()
    assert info is not None
    assert info.hwnd == 777
    assert info.pid == 888
    assert info.executable == "active.exe"
    assert info.title == "My Active Window"


def test_check_focus_match(automator):
    target = WindowInfo(
        hwnd=111, pid=222, executable="chrome.exe", title="Google - Google Chrome"
    )

    # Rule 1: HWND match
    active_hwnd_match = WindowInfo(
        hwnd=111, pid=999, executable="other.exe", title="Other"
    )
    assert automator.check_focus_match(active_hwnd_match, target) is True

    # Rule 2: PID match
    active_pid_match = WindowInfo(
        hwnd=999, pid=222, executable="other.exe", title="Other"
    )
    assert automator.check_focus_match(active_pid_match, target) is True

    # Rule 3: Executable and Title regex match
    active_regex_match = WindowInfo(
        hwnd=999, pid=999, executable="chrome.exe", title="Google Search"
    )
    assert (
        automator.check_focus_match(
            active_regex_match, target, window_title_pattern="Google"
        )
        is True
    )

    # Fail cases
    active_no_match = WindowInfo(
        hwnd=999, pid=999, executable="chrome.exe", title="Reddit"
    )
    assert (
        automator.check_focus_match(
            active_no_match, target, window_title_pattern="Google"
        )
        is False
    )
    assert automator.check_focus_match(None, target) is False


@patch("win32gui.EnumWindows")
@patch("win32gui.IsWindowVisible")
@patch("win32gui.GetWindowText")
@patch("win32process.GetWindowThreadProcessId")
@patch("psutil.Process")
def test_wait_for_window(
    mock_process_cls,
    mock_get_window_pid,
    mock_get_window_text,
    mock_is_visible,
    mock_enum_windows,
    automator,
):
    # Setup EnumWindows mock to invoke the callback with some fake HWNDs
    def fake_enum_windows(callback, extra):
        callback(101, extra)
        callback(102, extra)
        return True

    mock_enum_windows.side_effect = fake_enum_windows

    # Visible states
    mock_is_visible.side_effect = lambda hwnd: hwnd == 101 or hwnd == 102
    mock_get_window_text.side_effect = lambda hwnd: (
        "Visible App" if hwnd == 101 else "Another Visible App"
    )
    mock_get_window_pid.side_effect = lambda hwnd: (
        (None, 501) if hwnd == 101 else (None, 502)
    )

    mock_proc1 = MagicMock()
    mock_proc1.name.return_value = "app1.exe"
    mock_proc2 = MagicMock()
    mock_proc2.name.return_value = "app2.exe"

    mock_process_cls.side_effect = lambda pid: mock_proc1 if pid == 501 else mock_proc2

    # Find by PID candidate
    info = automator.wait_for_window(candidate_pids={501}, timeout=0.1)
    assert info is not None
    assert info.hwnd == 101
    assert info.pid == 501
    assert info.executable == "app1.exe"

    # Find by executable name
    info = automator.wait_for_window(executable_name="app2.exe", timeout=0.1)
    assert info is not None
    assert info.hwnd == 102
    assert info.executable == "app2.exe"

    # Find by title regex
    info = automator.wait_for_window(window_title_pattern="another", timeout=0.1)
    assert info is not None
    assert info.hwnd == 102
    assert info.title == "Another Visible App"

    # Empty search criteria should return None
    assert automator.wait_for_window(timeout=0.1) is None


@patch("core.execution.automator.os.path.exists")
@patch("core.execution.automator.subprocess.Popen")
@patch("core.execution.automator.os.startfile")
@patch("core.execution.automator.win32gui.GetWindowRect")
@patch("core.execution.automator.pyautogui.click")
def test_open_and_stabilize_app_success(
    mock_click, mock_rect, mock_startfile, mock_popen, mock_exists, automator
):
    mock_exists.return_value = True
    mock_rect.return_value = (10, 10, 110, 110)

    # Mock helpers on automator
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")

    automator.find_processes = MagicMock(side_effect=[{501, 502}, {501, 502, 503}])
    automator.wait_for_window = MagicMock(return_value=target_win)
    automator.activate_window_by_hwnd = MagicMock(return_value=True)
    automator.get_foreground_window_info = MagicMock(return_value=target_win)
    automator.check_focus_match = MagicMock(return_value=True)

    res = automator.open_and_stabilize_app("c:\\temp\\test.exe")
    assert res == target_win
    mock_popen.assert_called_once_with("c:\\temp\\test.exe")
    automator.activate_window_by_hwnd.assert_called_with(101)
    mock_click.assert_called_once_with(60, 60)


@patch("core.execution.automator.os.startfile")
def test_open_and_stabilize_app_window_timeout(mock_startfile, automator):
    automator.find_processes = MagicMock(return_value={501})
    automator.wait_for_window = MagicMock(return_value=None)

    with pytest.raises(TimeoutError, match="Window for .* not found"):
        automator.open_and_stabilize_app("https://example.com")


@patch("core.execution.automator.os.startfile")
def test_open_and_stabilize_app_focus_timeout(mock_startfile, automator):
    target_win = WindowInfo(hwnd=101, pid=503, executable="test.exe", title="Test App")
    other_win = WindowInfo(hwnd=999, pid=999, executable="other.exe", title="Other App")

    automator.find_processes = MagicMock(return_value={501})
    automator.wait_for_window = MagicMock(return_value=target_win)
    automator.activate_window_by_hwnd = MagicMock(return_value=True)
    automator.get_foreground_window_info = MagicMock(return_value=other_win)
    automator.check_focus_match = MagicMock(return_value=False)

    with pytest.raises(TimeoutError, match="Could not confirm foreground focus"):
        automator.open_and_stabilize_app("https://example.com")
