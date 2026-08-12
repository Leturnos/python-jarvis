from core.runtime.state import JarvisState
from core.ui.widgets.status_card import get_mode_badge_info


def test_get_mode_badge_info_hybrid_mode():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.IDLE)
    assert "Hybrid" in badge_text
    assert "Hey Jarvis" in tooltip or "Ctrl+Alt" in tooltip


def test_get_mode_badge_info_sleeping_state():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.SLEEPING)
    assert "Sleeping" in badge_text
    assert "descanso" in tooltip.lower() or "recursos" in tooltip.lower()
