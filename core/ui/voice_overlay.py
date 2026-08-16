from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QProgressBar, QWidget

from core.runtime.state import JarvisState


class VoiceOverlayHUD(QWidget):
    """Floating pill HUD for real-time voice interaction feedback."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(340, 50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(10)

        self.setStyleSheet(
            """
            QWidget#HUDContainer {
                background-color: rgba(25, 25, 25, 220);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 20px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                font-weight: 600;
            }
            QProgressBar {
                background-color: rgba(255, 255, 255, 20);
                border-radius: 4px;
                max-height: 6px;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 4px;
            }
            """
        )
        self.setObjectName("HUDContainer")

        self.icon_label = QLabel("🎙️", self)
        layout.addWidget(self.icon_label)

        self.status_label = QLabel("Jarvis Ready", self)
        layout.addWidget(self.status_label, stretch=1)

        self.vol_bar = QProgressBar(self)
        self.vol_bar.setRange(0, 100)
        self.vol_bar.setValue(0)
        self.vol_bar.setTextVisible(False)
        self.vol_bar.setFixedWidth(60)
        layout.addWidget(self.vol_bar)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def _reposition_bottom_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo: QRect = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 40
            self.move(QPoint(x, y))

    def update_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        state: JarvisState = snapshot.get("state", JarvisState.IDLE)
        status: str = snapshot.get("status", "Ready")
        volume: int = snapshot.get("volume", 0)

        self.status_label.setText(status)
        self.vol_bar.setValue(volume)

        state_icons = {
            JarvisState.LISTENING: "🎙️",
            JarvisState.THINKING: "🧠",
            JarvisState.EXECUTING: "⚡",
            JarvisState.MUTED: "🔇",
            JarvisState.SLEEPING: "🌙",
            JarvisState.ERROR: "⚠️",
        }
        self.icon_label.setText(state_icons.get(state, "🤖"))

        if state in (
            JarvisState.LISTENING,
            JarvisState.THINKING,
            JarvisState.EXECUTING,
        ):
            self.hide_timer.stop()
            self._reposition_bottom_center()
            if not self.isVisible():
                self.show()
        elif state == JarvisState.IDLE:
            if self.isVisible() and not self.hide_timer.isActive():
                self.hide_timer.start(3000)
        else:
            self.hide_timer.stop()
            if self.isVisible():
                self.hide()
