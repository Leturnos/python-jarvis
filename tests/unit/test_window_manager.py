from unittest.mock import MagicMock, patch

import pytest

from core.execution.window_manager import WindowManager


@pytest.fixture
def wm():
    return WindowManager()


@patch("psutil.process_iter")
def test_find_processes(mock_process_iter, wm):
    mock_p = MagicMock()
    mock_p.info = {"pid": 123, "name": "notepad.exe", "exe": "C:\\Windows\\notepad.exe"}
    mock_process_iter.return_value = [mock_p]

    pids = wm.find_processes(executable_name="notepad.exe")
    assert pids == {123}
