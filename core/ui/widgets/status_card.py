from typing import Any

from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel, ProgressBar, SimpleCardWidget, TitleLabel

from core.infra.config import config
from core.runtime.state import JarvisState


def get_mode_badge_info(
    activation_mode: str, current_state: JarvisState, shortcut: str | None = None
) -> tuple[str, str]:
    """Returns badge text and tooltip description for active mode and state."""
    if current_state == JarvisState.SLEEPING:
        return (
            "Sleeping (Dormindo)",
            "Jarvis está em modo de descanso para economizar recursos. Use a bandeja para acordar.",
        )
    if current_state == JarvisState.MUTED:
        return (
            "Muted (Silenciado)",
            "Jarvis está silenciado. Clique para reativar o microfone.",
        )

    if not shortcut:
        try:
            shortcut = (
                config.get("voice_activation", {})
                .get("push_to_talk", {})
                .get("key", "ctrl+alt")
            )
        except Exception:
            shortcut = "ctrl+alt"

    formatted_shortcut = (
        "+".join(p.strip().capitalize() for p in shortcut.split("+"))
        if shortcut
        else "Ctrl+Alt"
    )

    mode_map = {
        "push_to_talk": (
            f"Push-to-Talk ({formatted_shortcut})",
            f"Pressione e segure {formatted_shortcut} para falar.",
        ),
        "always_listening": (
            "Always Listening (Voz)",
            "Ouvindo continuamente a frase 'Hey Jarvis'.",
        ),
        "hybrid": (
            f"Hybrid (Voz + {formatted_shortcut})",
            f"Ativo por palavra de ativação 'Hey Jarvis' ou atalho {formatted_shortcut}.",
        ),
        "disabled": ("Disabled (Desativado)", "Ativação de voz desativada."),
    }
    return mode_map.get(activation_mode, ("Ready", "Assistente pronto."))


class StatusCardWidget(SimpleCardWidget):
    def __init__(self, wakeword_name: str, parent: Any = None) -> None:
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(10)

        self.title = TitleLabel("Jarvis Status")
        self.layout.addWidget(self.title)

        self.wakeword_label = BodyLabel(f"Listening for: {wakeword_name}")
        self.wakeword_label.setObjectName("WakeWordLabel")
        self.layout.addWidget(self.wakeword_label)

        self.mode_label = BodyLabel("Mode: Initializing...")
        self.mode_label.setObjectName("ModeLabel")
        self.layout.addWidget(self.mode_label)

        self.state_label = BodyLabel("State: IDLE")
        self.state_label.setObjectName("StateLabel")
        self.layout.addWidget(self.state_label)

        self.status_label = BodyLabel("Status: Initializing...")
        self.layout.addWidget(self.status_label)

        self.score_label = BodyLabel("Wake Word Score: 0.00")
        self.layout.addWidget(self.score_label)

        self.vol_progress = ProgressBar()
        self.vol_progress.setRange(0, 100)
        self.vol_progress.setValue(0)
        self.layout.addWidget(self.vol_progress)

    def update_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.status_label.setText(f"Status: {snapshot['status']}")
        self.score_label.setText(f"Wake Word Score: {snapshot['score']:.2f}")
        self.vol_progress.setValue(snapshot["volume"])

        # Mode & Tooltip update
        activation_mode = snapshot.get("mode", "hybrid")
        state = snapshot.get("state", JarvisState.IDLE)
        badge_text, tooltip = get_mode_badge_info(activation_mode, state)
        self.mode_label.setText(f"Mode: {badge_text}")
        self.mode_label.setToolTip(tooltip)

        # State Colors handling
        self.state_label.setText(f"State: {state.name}")

        state_colors = {
            "IDLE": "#00ff00",
            "LISTENING": "#ffff00",
            "THINKING": "#ff00ff",
            "CONFIRMING_DRY_RUN": "#0000ff",
            "EXECUTING": "#ff0000",
            "MUTED": "#888888",
            "ERROR": "#ff5555",
        }
        color = state_colors.get(state.name, "white")
        self.state_label.setStyleSheet(f"color: {color};")
