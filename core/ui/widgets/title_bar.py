"""Shared frameless custom title bar and close button for Jarvis windows."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from core.shared.utils import get_resources_dir


class CloseTitleButton(QPushButton):
    """Minimalist custom vector X close button inspired by FxSound."""

    def __init__(
        self,
        parent: QWidget | None = None,
        close_tooltip: str = "Ocultar na bandeja",
        width: int = 34,
        height: int = 30,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(close_tooltip)
        self._hovered = False
        self.setStyleSheet("background: transparent; border: none;")

    def enterEvent(self, event: Any) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hovered:
            painter.setBrush(QColor(255, 59, 92, 36))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 6, 6)

        pen_color = QColor("#ff5c77") if self._hovered else QColor("#ff3b5c")
        pen = QPen(pen_color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half = 4.5
        painter.drawLine(
            QPointF(cx - half, cy - half),
            QPointF(cx + half, cy + half),
        )
        painter.drawLine(
            QPointF(cx + half, cy - half),
            QPointF(cx - half, cy + half),
        )


class CustomTitleBar(QFrame):
    """Frameless custom top bar with Jarvis icon, title, drag support, and close button."""

    close_clicked = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "Jarvis",
        close_tooltip: str = "Ocultar na bandeja",
        bar_height: int = 42,
        show_icon: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(bar_height)
        self._drag_pos: QPoint | None = None

        self.setStyleSheet(
            """
            QFrame#CustomTitleBar {
                background-color: #151518;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            }
            QLabel#TitleBarLabel {
                color: #ededf0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13.5px;
                font-weight: 600;
                background: transparent;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        self.icon_label: QLabel | None = None
        if show_icon:
            icon_path = get_resources_dir() / "icon.ico"
            if icon_path.exists():
                icon_size = 18 if bar_height < 40 else 20
                pixmap = QIcon(str(icon_path)).pixmap(icon_size, icon_size)
                if not pixmap.isNull():
                    self.icon_label = QLabel(self)
                    self.icon_label.setStyleSheet("background: transparent;")
                    self.icon_label.setPixmap(pixmap)
                    layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("TitleBarLabel")
        layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self.close_btn = CloseTitleButton(self, close_tooltip=close_tooltip)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win is not None:
                self._drag_pos = (
                    event.globalPosition().toPoint() - win.frameGeometry().topLeft()
                )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            win = self.window()
            if win is not None:
                win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # Prevent maximize on double click
        event.accept()
