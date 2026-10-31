from unittest.mock import MagicMock, patch

from core.infra.config import config
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


def test_status_card_minimalist_orb_and_three_mode_buttons():
    from PySide6.QtWidgets import QApplication

    from core.runtime.state import state_manager
    from core.ui.widgets.status_card import StatusCardWidget

    _ = QApplication.instance() or QApplication([])
    card = StatusCardWidget(wakeword_name="hey_jarvis")

    assert hasattr(card, "mic_orb")
    assert card.hybrid_btn.text() == "Híbrido (Voz + Ctrl+Alt)"
    assert card.ptt_btn.text() == "Aperte para Falar"
    assert card.mute_btn.text() == "Silenciar"

    with patch("core.ui.widgets.status_card.update_yaml_voice_mode") as mock_yaml:
        card.ptt_btn.click()
        mock_yaml.assert_called_once_with("push_to_talk")

    state_manager.set_state(JarvisState.IDLE)
    card.mute_btn.click()
    assert state_manager.get_state() == JarvisState.MUTED
    card.mute_btn.click()
    assert state_manager.get_state() == JarvisState.IDLE


def test_status_card_ptt_mode_selection_and_persistence_across_snapshots():
    from PySide6.QtWidgets import QApplication

    from core.ui.widgets.status_card import StatusCardWidget

    _ = QApplication.instance() or QApplication([])
    mock_adapter = MagicMock()
    card = StatusCardWidget(wakeword_name="hey_jarvis", ui_adapter=mock_adapter)

    with patch("core.ui.widgets.status_card.update_yaml_voice_mode") as mock_yaml:
        card.ptt_btn.click()
        mock_yaml.assert_called_once_with("push_to_talk")
        mock_adapter.set_mode.assert_called_once_with("push_to_talk")
        assert config["voice_activation"]["mode"] == "push_to_talk"

    # Subsequent snapshot from audio loop without 'mode' must NOT revert to hybrid
    card.update_from_snapshot(
        {
            "status": "Ready",
            "score": 0.0,
            "volume": 0,
            "state": JarvisState.IDLE,
        }
    )
    assert "Aperte para Falar" in card.mode_label.text()
