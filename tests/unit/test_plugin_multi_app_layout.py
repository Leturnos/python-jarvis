import sys
from unittest.mock import MagicMock, patch

for mod in [
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

from core.execution.plan_builder import PlanBuilder  # noqa: E402


def test_build_plugin_plan_parses_window_state():
    config = {}
    builder = PlanBuilder(config)

    mock_actions = [
        {
            "type": "system_open",
            "target": r"C:\Windows\notepad.exe",
            "window_state": "snap_left",
        },
        {
            "type": "system_open",
            "target": r"C:\Windows\System32\cmd.exe",
            "window_state": "snap_right",
        },
    ]

    with patch(
        "core.plugins.plugin_manager.plugin_manager.get_actions_for_intent",
        return_value=mock_actions,
    ):
        plan = builder.build_plugin_plan({"intent": "dev_workspace"})

        assert len(plan.steps) == 2
        assert plan.steps[0].payload.get("window_state") == "snap_left"
        assert plan.steps[1].payload.get("window_state") == "snap_right"
