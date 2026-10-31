import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ProgressBar, SimpleCardWidget, TitleLabel

from core.infra.config import config, update_yaml_voice_mode
from core.runtime.state import JarvisState, state_manager
from core.shared.utils import get_resources_dir

STATE_DISPLAY_NAMES_PT: dict[JarvisState, str] = {
    JarvisState.IDLE: "Pronto para Ouvir",
    JarvisState.LISTENING: "Ouvindo...",
    JarvisState.THINKING: "Processando...",
    JarvisState.CONFIRMING_DRY_RUN: "Aguardando Confirmação",
    JarvisState.EXECUTING: "Executando...",
    JarvisState.MUTED: "Silenciado",
    JarvisState.SLEEPING: "Dormindo (Pausado)",
    JarvisState.ERROR: "Erro",
}


def get_mode_badge_info(
    activation_mode: str, current_state: JarvisState, shortcut: str | None = None
) -> tuple[str, str]:
    """Returns badge text and tooltip description for active mode and state."""
    if current_state == JarvisState.SLEEPING:
        return (
            "Dormindo (Pausado)",
            "Jarvis está em modo de descanso para economizar recursos. Use a bandeja para acordar.",
        )
    if current_state == JarvisState.MUTED:
        return (
            "Silenciado",
            "Jarvis está silenciado. Clique na bandeja para reativar o microfone.",
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
            f"Aperte para Falar ({formatted_shortcut})",
            f"Pressione e segure {formatted_shortcut} para falar.",
        ),
        "always_listening": (
            "Ativação por Voz Contínua",
            "Ouvindo continuamente a frase 'Hey Jarvis'.",
        ),
        "hybrid": (
            f"Híbrido (Voz ou {formatted_shortcut})",
            f"Ativo por palavra de ativação 'Hey Jarvis' ou atalho {formatted_shortcut}.",
        ),
        "disabled": ("Desativado", "Ativação de voz desativada."),
    }
    return mode_map.get(activation_mode, ("Pronto", "Assistente pronto."))


class PulsingMicOrb(QWidget):
    """Animated blue-pulsing microphone orb for the minimalist home dashboard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(96, 96)
        self._phase = 0.0
        self._state = JarvisState.IDLE

        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state: JarvisState) -> None:
        if self._state != state:
            self._state = state
            self.update()

    def _tick(self) -> None:
        speed = 0.16 if self._state == JarvisState.LISTENING else 0.08
        self._phase = (self._phase + speed) % (2 * math.pi)
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_r = 33.0
        pulse = (math.sin(self._phase) + 1.0) / 2.0  # 0.0 -> 1.0

        if self._state in (JarvisState.MUTED, JarvisState.SLEEPING):
            primary_color = QColor(120, 120, 135)
            glow_alpha = 20
            ring_r = base_r + 2.0
        elif self._state == JarvisState.LISTENING:
            primary_color = QColor(0, 210, 255)
            glow_alpha = int(55 + 75 * pulse)
            ring_r = base_r + 4.0 + 8.0 * pulse
        elif self._state in (JarvisState.THINKING, JarvisState.EXECUTING):
            primary_color = QColor(56, 182, 255)
            glow_alpha = int(45 + 60 * pulse)
            ring_r = base_r + 3.0 + 6.0 * pulse
        else:
            primary_color = QColor(0, 150, 255)
            glow_alpha = int(30 + 50 * pulse)
            ring_r = base_r + 2.0 + 6.5 * pulse

        # Outer expanding pulse ring
        outer_color = QColor(
            primary_color.red(),
            primary_color.green(),
            primary_color.blue(),
            int(glow_alpha * (1.0 - 0.55 * pulse)),
        )
        painter.setPen(QPen(outer_color, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # Inner radial gradient orb
        grad = QRadialGradient(QPointF(cx, cy), base_r)
        grad.setColorAt(
            0.0,
            QColor(
                primary_color.red(),
                primary_color.green(),
                primary_color.blue(),
                68,
            ),
        )
        grad.setColorAt(
            1.0,
            QColor(
                primary_color.red(),
                primary_color.green(),
                primary_color.blue(),
                14,
            ),
        )
        painter.setBrush(grad)
        painter.setPen(QPen(primary_color, 2.0))
        painter.drawEllipse(QPointF(cx, cy), base_r, base_r)

        # Draw vector microphone icon in center
        icon_pen = QPen(QColor("#e8f4ff"), 2.1)
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        icon_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(icon_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Mic capsule
        capsule_rect = QRectF(cx - 5.0, cy - 12.0, 10.0, 14.0)
        painter.drawRoundedRect(capsule_rect, 5.0, 5.0)

        # U-shaped cradle arc
        arc_rect = QRectF(cx - 9.5, cy - 8.5, 19.0, 15.0)
        painter.drawArc(arc_rect, 0 * 16, -180 * 16)

        # Vertical stand and base
        painter.drawLine(QPointF(cx, cy + 6.5), QPointF(cx, cy + 11.5))
        painter.drawLine(QPointF(cx - 5.0, cy + 11.5), QPointF(cx + 5.0, cy + 11.5))


class StatusCardWidget(SimpleCardWidget):
    """Minimalist home status dashboard with pulsing blue mic orb and mode toggles."""

    def __init__(
        self,
        wakeword_name: str,
        parent: Any = None,
        ui_adapter: Any = None,
    ) -> None:
        super().__init__(parent)
        self.wakeword_name = wakeword_name
        self.ui_adapter = ui_adapter
        self.setObjectName("MinimalStatusCard")
        self.setStyleSheet(
            """
            SimpleCardWidget#MinimalStatusCard {
                background-color: #17171b;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
            }
            """
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Retain logo_label and title attributes for backward compatibility
        self.logo_label = QLabel(self)
        self.logo_label.setVisible(False)
        icon_path = get_resources_dir() / "icon.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(32, 32)
            if not pixmap.isNull():
                self.logo_label.setPixmap(pixmap)

        self.title = TitleLabel("Status do Jarvis", self)
        self.title.setVisible(False)

        self.layout.addStretch(1)

        # 1. Center Pulsing Microphone Orb
        orb_row = QHBoxLayout()
        orb_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mic_orb = PulsingMicOrb(self)
        orb_row.addWidget(self.mic_orb)
        self.layout.addLayout(orb_row)

        # 2. Main State Display Heading (e.g. "Estado: Pronto" / "Pronto para Ouvir")
        self.state_label = BodyLabel("Estado: Pronto", self)
        self.state_label.setObjectName("StateLabel")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet(
            "font-size: 19px; font-weight: 700; color: #ffffff;"
        )
        self.layout.addWidget(self.state_label)

        # 3. Unified Subtitle Row (Wakeword + Confidence Score)
        info_row = QHBoxLayout()
        info_row.setSpacing(10)
        info_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.wakeword_label = BodyLabel(f"Palavra de ativação: {wakeword_name}", self)
        self.wakeword_label.setObjectName("WakeWordLabel")
        self.wakeword_label.setStyleSheet("color: #9a9aa8; font-size: 12.5px;")
        info_row.addWidget(self.wakeword_label)

        sep_lbl = BodyLabel("•", self)
        sep_lbl.setStyleSheet("color: #555562; font-size: 12.5px;")
        info_row.addWidget(sep_lbl)

        self.score_label = BodyLabel("Pontuação da Escuta: 0.00", self)
        self.score_label.setStyleSheet("color: #38b6ff; font-size: 12.5px;")
        info_row.addWidget(self.score_label)

        self.layout.addLayout(info_row)

        # Hidden compatibility labels (kept updated for unit tests & internal readers)
        self.mode_label = BodyLabel("Modo: Inicializando...", self)
        self.mode_label.setObjectName("ModeLabel")
        self.mode_label.setVisible(False)

        self.status_label = BodyLabel("Status: Inicializando...", self)
        self.status_label.setVisible(False)

        self.layout.addSpacing(8)

        # 4. Centered Audio Volume Meter
        meter_row = QHBoxLayout()
        meter_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol_progress = ProgressBar(self)
        self.vol_progress.setRange(0, 100)
        self.vol_progress.setValue(0)
        self.vol_progress.setFixedWidth(300)
        meter_row.addWidget(self.vol_progress)
        self.layout.addLayout(meter_row)

        self.layout.addSpacing(14)

        # 5. Three Real Mode Pill Buttons (Híbrido | Aperte para Falar | Silenciar)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hybrid_btn = QPushButton("Híbrido (Voz + Ctrl+Alt)", self)
        self.hybrid_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hybrid_btn.clicked.connect(lambda: self._select_mode("hybrid"))
        btn_row.addWidget(self.hybrid_btn)

        self.ptt_btn = QPushButton("Aperte para Falar", self)
        self.ptt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ptt_btn.clicked.connect(lambda: self._select_mode("push_to_talk"))
        btn_row.addWidget(self.ptt_btn)

        self.mute_btn = QPushButton("Silenciar", self)
        self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_btn.clicked.connect(self._toggle_mute)
        btn_row.addWidget(self.mute_btn)

        self.layout.addLayout(btn_row)
        self.layout.addStretch(1)

        current_mode = config.get("voice_activation", {}).get("mode", "hybrid")
        self._refresh_mode_buttons(current_mode, state_manager.get_state())

    def _select_mode(self, mode: str) -> None:
        config.setdefault("voice_activation", {})["mode"] = mode
        try:
            update_yaml_voice_mode(mode)
        except Exception:
            pass
        if self.ui_adapter:
            self.ui_adapter.set_mode(mode)
        if state_manager.get_state() in (JarvisState.MUTED, JarvisState.SLEEPING):
            state_manager.set_state(JarvisState.IDLE)
        self._refresh_mode_buttons(mode, state_manager.get_state())

    def _toggle_mute(self) -> None:
        cur = state_manager.get_state()
        if cur == JarvisState.MUTED:
            state_manager.set_state(JarvisState.IDLE)
        else:
            state_manager.set_state(JarvisState.MUTED)
        mode = config.get("voice_activation", {}).get("mode", "hybrid")
        self._refresh_mode_buttons(mode, state_manager.get_state())

    def _refresh_mode_buttons(
        self, active_mode: str, current_state: JarvisState
    ) -> None:
        is_muted = current_state == JarvisState.MUTED

        base_style = """
            QPushButton {
                background-color: #1e1e24;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px;
                padding: 7px 14px;
                color: #b0b0bc;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #26262e;
                color: #ffffff;
            }
        """
        active_style = """
            QPushButton {
                background-color: rgba(0, 120, 212, 0.20);
                border: 1px solid #0078d4;
                border-radius: 6px;
                padding: 7px 14px;
                color: #66b8ff;
                font-size: 12px;
                font-weight: 600;
            }
        """
        muted_active_style = """
            QPushButton {
                background-color: rgba(255, 59, 92, 0.18);
                border: 1px solid #ff3b5c;
                border-radius: 6px;
                padding: 7px 14px;
                color: #ff6b84;
                font-size: 12px;
                font-weight: 600;
            }
        """

        self.hybrid_btn.setStyleSheet(
            active_style if (not is_muted and active_mode == "hybrid") else base_style
        )
        self.ptt_btn.setStyleSheet(
            active_style
            if (not is_muted and active_mode == "push_to_talk")
            else base_style
        )
        self.mute_btn.setStyleSheet(muted_active_style if is_muted else base_style)

    def update_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        raw_status = snapshot.get("status", "")
        status = "Pronto" if raw_status == "Ready" else raw_status
        self.status_label.setText(f"Status: {status}")
        self.score_label.setText(f"Pontuação da Escuta: {snapshot['score']:.2f}")
        self.vol_progress.setValue(snapshot["volume"])

        # Mode & Tooltip update
        activation_mode = snapshot.get("mode") or config.get(
            "voice_activation", {}
        ).get("mode", "hybrid")
        state = snapshot.get("state", JarvisState.IDLE)
        badge_text, tooltip = get_mode_badge_info(activation_mode, state)
        self.mode_label.setText(f"Modo: {badge_text}")
        self.mode_label.setToolTip(tooltip)

        self.mic_orb.set_state(state)
        self._refresh_mode_buttons(activation_mode, state)

        # State Colors handling
        state_text = STATE_DISPLAY_NAMES_PT.get(state, state.name)
        self.state_label.setText(f"Estado: {state_text}")

        state_colors = {
            "IDLE": "#ffffff",
            "LISTENING": "#38b6ff",
            "THINKING": "#a855f7",
            "CONFIRMING_DRY_RUN": "#f39c12",
            "EXECUTING": "#2ecc71",
            "MUTED": "#888888",
            "ERROR": "#ff5555",
        }
        color = state_colors.get(state.name, "white")
        self.state_label.setStyleSheet(
            f"font-size: 19px; font-weight: 700; color: {color};"
        )
