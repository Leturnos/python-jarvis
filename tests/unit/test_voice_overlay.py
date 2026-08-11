from PySide6.QtWidgets import QApplication

from core.runtime.state import JarvisState
from core.ui.voice_overlay import VoiceOverlayHUD


def test_voice_overlay_state_update():
    _ = QApplication.instance() or QApplication([])
    hud = VoiceOverlayHUD()

    snapshot = {
        "status": "Ouvindo...",
        "score": 0.85,
        "volume": 45,
        "state": JarvisState.LISTENING,
    }
    hud.update_from_snapshot(snapshot)

    assert hud.isVisible() is True
    assert hud.status_label.text() == "Ouvindo..."
