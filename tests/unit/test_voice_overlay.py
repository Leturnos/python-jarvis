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


def test_voice_overlay_initial_and_ready():
    _ = QApplication.instance() or QApplication([])
    hud = VoiceOverlayHUD()

    assert hud.status_label.text() == "Jarvis Pronto"

    snapshot = {
        "status": "Ready",
        "score": 0.0,
        "volume": 0,
        "state": JarvisState.IDLE,
    }
    hud.update_from_snapshot(snapshot)
    assert hud.status_label.text() == "Pronto"
