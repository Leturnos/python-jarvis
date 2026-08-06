import sys
from unittest.mock import MagicMock

for mod in [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "qfluentwidgets",
    "qdarktheme",
]:
    sys.modules[mod] = MagicMock()

from core.runtime.state import JarvisState  # noqa: E402
from core.ui.widgets.status_card import get_mode_badge_info  # noqa: E402


def test_get_mode_badge_info_hybrid_mode():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.IDLE)
    assert "Hybrid" in badge_text
    assert "Hey Jarvis" in tooltip or "Ctrl+Alt" in tooltip


def test_get_mode_badge_info_sleeping_state():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.SLEEPING)
    assert "Sleeping" in badge_text
    assert "descanso" in tooltip.lower() or "recursos" in tooltip.lower()
