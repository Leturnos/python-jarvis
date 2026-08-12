from unittest.mock import patch

from core.execution.step_executor import poll_window_handle


def test_poll_window_handle_returns_hwnd_when_found():
    with patch(
        "core.execution.step_executor.find_window_handle", side_effect=[0, 12345]
    ):
        hwnd = poll_window_handle("Spotify", timeout=1.0, interval=0.05)
        assert hwnd == 12345


def test_poll_window_handle_returns_zero_on_timeout():
    with patch("core.execution.step_executor.find_window_handle", return_value=0):
        hwnd = poll_window_handle("NonExistentApp", timeout=0.2, interval=0.05)
        assert hwnd == 0
