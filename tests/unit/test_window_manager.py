from unittest.mock import MagicMock, patch

import pytest

from core.execution.window_manager import WindowManager


@pytest.fixture
def wm():
    return WindowManager()


@patch("core.execution.window_manager.psutil.process_iter")
def test_find_processes(mock_process_iter, wm):
    mock_p = MagicMock()
    mock_p.info = {"pid": 123, "name": "notepad.exe", "exe": "C:\\Windows\\notepad.exe"}
    mock_process_iter.return_value = [mock_p]

    pids = wm.find_processes(executable_name="notepad.exe")
    assert pids == {123}


@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_url_returns_promptly_without_timeout(
    mock_startfile, wm
):
    mock_startfile.return_value = None
    wm.open_and_stabilize_app("https://mail.google.com")
    mock_startfile.assert_called_once_with("https://mail.google.com")


@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_uri_scheme_returns_promptly(mock_startfile, wm):
    mock_startfile.return_value = None
    wm.open_and_stabilize_app("ms-settings:")
    mock_startfile.assert_called_once_with("ms-settings:")


@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_normalizes_calc(mock_startfile, wm):
    from core.execution.window_manager import WindowInfo

    mock_startfile.return_value = None
    calc_win = WindowInfo(
        hwnd=111, pid=222, executable="CalculatorApp.exe", title="Calculadora"
    )
    with patch.object(wm, "wait_for_window", return_value=calc_win) as mock_wait:
        with patch.object(wm, "activate_window_by_hwnd", return_value=True):
            with patch.object(wm, "get_foreground_window_info", return_value=calc_win):
                with patch.object(wm, "check_focus_match", return_value=True):
                    win = wm.open_and_stabilize_app("calc:")
                    assert win == calc_win
                    mock_startfile.assert_called_once_with("calc.exe")
                    mock_wait.assert_called_once_with(
                        candidate_pids=set(),
                        executable_name="calc.exe",
                        window_title_pattern="Calculadora|Calculator",
                        timeout=10.0,
                    )


@patch("core.execution.window_manager.os.path.isdir")
@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_directory_expands_vars(mock_startfile, mock_isdir, wm):
    mock_isdir.return_value = True
    wm.open_and_stabilize_app("%USERPROFILE%\\Downloads")
    mock_startfile.assert_called_once()
    assert "%USERPROFILE%" not in mock_startfile.call_args[0][0]


@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_url_with_pattern_waits_for_window(mock_startfile, wm):
    from core.execution.window_manager import WindowInfo

    target_win = WindowInfo(
        hwnd=999, pid=1234, executable="chrome.exe", title="Gmail - Inbox"
    )
    with patch.object(wm, "wait_for_window", return_value=target_win) as mock_wait:
        with patch.object(wm, "activate_window_by_hwnd", return_value=True):
            with patch.object(
                wm, "get_foreground_window_info", return_value=target_win
            ):
                with patch.object(wm, "check_focus_match", return_value=True):
                    win = wm.open_and_stabilize_app(
                        "https://mail.google.com", window_title_pattern="Gmail"
                    )
                    assert win == target_win
                    mock_wait.assert_called_once()


@patch("core.execution.window_manager.os.startfile")
def test_open_and_stabilize_app_missing_criteria_returns_promptly(mock_startfile, wm):
    with patch.object(wm, "find_processes", return_value={10, 20}):
        wm.open_and_stabilize_app("custom_tool")
        mock_startfile.assert_called_once_with("custom_tool")


@patch("core.execution.window_manager.psutil.Process")
@patch("core.execution.window_manager.win32process.GetWindowThreadProcessId")
@patch("core.execution.window_manager.win32gui.GetWindowText")
@patch("core.execution.window_manager.win32gui.IsWindowVisible")
@patch("core.execution.window_manager.win32gui.EnumWindows")
def test_wait_for_window_matches_title_pattern_despite_executable_mismatch(
    mock_enum_windows,
    mock_is_visible,
    mock_get_text,
    mock_get_pid,
    mock_psutil_proc,
    wm,
):
    mock_is_visible.return_value = True
    mock_get_text.return_value = "Calculadora"
    mock_get_pid.return_value = (0, 5000)
    proc_mock = MagicMock()
    proc_mock.name.return_value = "CalculatorApp.exe"
    mock_psutil_proc.return_value = proc_mock

    def fake_enum(cb, extra):
        cb(101, extra)

    mock_enum_windows.side_effect = fake_enum

    # Even though executable_name is "calc.exe" and process is "CalculatorApp.exe",
    # the title pattern "Calculadora|Calculator" must match immediately
    win = wm.wait_for_window(
        candidate_pids=set(),
        executable_name="calc.exe",
        window_title_pattern="Calculadora|Calculator",
        timeout=1.0,
    )
    assert win is not None
    assert win.hwnd == 101
    assert win.title == "Calculadora"
    assert win.executable == "CalculatorApp.exe"


@patch("core.execution.window_manager.psutil.Process")
@patch("core.execution.window_manager.win32process.GetWindowThreadProcessId")
@patch("core.execution.window_manager.win32gui.GetWindowText")
@patch("core.execution.window_manager.win32gui.IsWindowVisible")
@patch("core.execution.window_manager.win32gui.EnumWindows")
def test_wait_for_window_matches_candidate_pids(
    mock_enum_windows,
    mock_is_visible,
    mock_get_text,
    mock_get_pid,
    mock_psutil_proc,
    wm,
):
    mock_is_visible.return_value = True
    mock_get_text.return_value = "Untitled - Notepad"
    mock_get_pid.return_value = (0, 6000)
    proc_mock = MagicMock()
    proc_mock.name.return_value = "notepad.exe"
    mock_psutil_proc.return_value = proc_mock

    def fake_enum(cb, extra):
        cb(202, extra)

    mock_enum_windows.side_effect = fake_enum

    win = wm.wait_for_window(
        candidate_pids={6000},
        executable_name="notepad.exe",
        timeout=1.0,
    )
    assert win is not None
    assert win.hwnd == 202
    assert win.pid == 6000


@patch("core.execution.window_manager.psutil.Process")
@patch("core.execution.window_manager.win32process.GetWindowThreadProcessId")
@patch("core.execution.window_manager.win32gui.GetWindowText")
@patch("core.execution.window_manager.win32gui.IsWindowVisible")
@patch("core.execution.window_manager.win32gui.EnumWindows")
def test_wait_for_window_matches_executable_name_fallback(
    mock_enum_windows,
    mock_is_visible,
    mock_get_text,
    mock_get_pid,
    mock_psutil_proc,
    wm,
):
    mock_is_visible.return_value = True
    mock_get_text.return_value = "Untitled - Notepad"
    mock_get_pid.return_value = (0, 7000)
    proc_mock = MagicMock()
    proc_mock.name.return_value = "notepad.exe"
    mock_psutil_proc.return_value = proc_mock

    def fake_enum(cb, extra):
        cb(303, extra)

    mock_enum_windows.side_effect = fake_enum

    # candidate_pids empty (app already running), but executable matches
    win = wm.wait_for_window(
        candidate_pids=set(),
        executable_name="notepad.exe",
        timeout=1.0,
    )
    assert win is not None
    assert win.hwnd == 303
    assert win.executable == "notepad.exe"
