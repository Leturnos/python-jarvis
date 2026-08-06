import sys
from unittest.mock import MagicMock, patch

for mod in [
    "numpy",
    "psutil",
    "pyautogui",
    "pyperclip",
    "win32gui",
    "win32con",
    "win32process",
    "win32api",
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    "pyttsx3",
    "cv2",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "plyer",
    "qdarktheme",
]:
    sys.modules[mod] = MagicMock()

from core.execution.step_executor import poll_window_handle  # noqa: E402


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
