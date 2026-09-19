from core.runtime.state import JarvisState
from core.ui.widgets.status_card import get_mode_badge_info


def test_get_mode_badge_info_hybrid_mode():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.IDLE)
    assert "Híbrido" in badge_text
    assert "Hey Jarvis" in tooltip or "Ctrl+Alt" in tooltip


def test_get_mode_badge_info_sleeping_state():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.SLEEPING)
    assert "Dormindo" in badge_text
    assert "descanso" in tooltip.lower() or "recursos" in tooltip.lower()


def test_get_mode_badge_info_muted_state():
    badge_text, tooltip = get_mode_badge_info("hybrid", JarvisState.MUTED)
    assert "Silenciado" in badge_text


def test_get_mode_badge_info_push_to_talk():
    badge_text, tooltip = get_mode_badge_info("push_to_talk", JarvisState.IDLE)
    assert "Aperte para Falar" in badge_text


def test_get_mode_badge_info_always_listening():
    badge_text, tooltip = get_mode_badge_info("always_listening", JarvisState.IDLE)
    assert "Ativação por Voz Contínua" in badge_text


def test_status_card_widget_pt_labels():
    from PySide6.QtWidgets import QApplication

    from core.ui.widgets.status_card import StatusCardWidget

    _ = QApplication.instance() or QApplication([])
    card = StatusCardWidget(wakeword_name="jarvis")

    assert card.title.text() == "Status do Jarvis"
    assert card.wakeword_label.text() == "Palavra de ativação: jarvis"
    assert card.mode_label.text() == "Modo: Inicializando..."
    assert card.state_label.text() == "Estado: Pronto"
    assert card.status_label.text() == "Status: Inicializando..."
    assert card.score_label.text() == "Pontuação da Escuta: 0.00"

    card.update_from_snapshot(
        {
            "status": "Ready",
            "score": 0.95,
            "volume": 20,
            "mode": "hybrid",
            "state": JarvisState.LISTENING,
        }
    )
    assert card.status_label.text() == "Status: Pronto"
    assert card.score_label.text() == "Pontuação da Escuta: 0.95"
    assert "Modo: Híbrido" in card.mode_label.text()
    assert card.state_label.text() == "Estado: Ouvindo..."
