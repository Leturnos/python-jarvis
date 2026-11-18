"""Frameless non-intrusive Desktop HUD notification cards (Jarvis 3B visual channel)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.shared.utils import get_resources_dir
from core.ui.feedback import build_obsidian_card_qss, get_severity_style


class DesktopNotificationToast(QWidget):
    """Frameless top-level desktop notification aligned with SecurityDialogWidget."""

    dismissed = Signal(object)

    def __init__(
        self,
        title: str,
        message: str,
        duration_ms: int = 3500,
        level: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.level = level.lower()
        self.style_spec = get_severity_style(self.level)
        self.duration_ms = max(1200, int(duration_ms))
        self._remaining_ms = self.duration_ms
        self._is_closing = False
        self._pos_anim: QPropertyAnimation | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._exit_group: QParallelAnimationGroup | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(348)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.card_frame = QFrame(self)
        self.card_frame.setObjectName("DesktopNotificationCard")
        self.card_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card_frame.setStyleSheet(
            build_obsidian_card_qss(
                "DesktopNotificationCard",
                self.style_spec.accent_hex,
                border_radius=11,
                bg_rgba="rgba(20, 21, 27, 245)",
            )
        )
        outer_layout.addWidget(self.card_frame)

        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(13, 11, 11, 9)
        card_layout.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_path = get_resources_dir() / "icon.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(22, 22)
            if not pixmap.isNull():
                icon_lbl = QLabel(self.card_frame)
                icon_lbl.setPixmap(pixmap)
                top_row.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.title_label = QLabel(title, self.card_frame)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "color: #ffffff; font-family: 'Segoe UI', sans-serif; "
            "font-size: 12.5px; font-weight: 700;"
        )
        text_col.addWidget(self.title_label)

        self.message_label = QLabel(message, self.card_frame)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            "color: #c9cad6; font-family: 'Segoe UI', sans-serif; "
            "font-size: 12px; font-weight: 400;"
        )
        text_col.addWidget(self.message_label)

        top_row.addLayout(text_col, 1)

        self.close_btn = QPushButton("✕", self.card_frame)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Dispensar")
        self.close_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 5px;
                color: #848595;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
            """
        )
        self.close_btn.clicked.connect(self.dismiss)
        top_row.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)

        card_layout.addLayout(top_row)

        self.progress_bar = QProgressBar(self.card_frame)
        self.progress_bar.setRange(0, self.duration_ms)
        self.progress_bar.setValue(self.duration_ms)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.07);
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {self.style_spec.accent_hex};
                border-radius: 1px;
            }}
            """
        )
        card_layout.addWidget(self.progress_bar)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._on_tick)

        self.adjustSize()

    def _animate_pos(
        self, start: QPoint, end: QPoint, duration: int, curve: QEasingCurve.Type
    ) -> None:
        if self._pos_anim is not None:
            self._pos_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(curve)
        self._pos_anim = anim
        anim.start()

    def play_enter(self, target_pos: QPoint) -> None:
        """Slides in from the right edge with smooth opacity fade-in."""
        if self._is_closing:
            return
        start_pos = QPoint(target_pos.x() + 24, target_pos.y())
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()

        self._animate_pos(start_pos, target_pos, 200, QEasingCurve.Type.OutCubic)

        if self._fade_anim is not None:
            self._fade_anim.stop()
        fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        fade_anim.setDuration(200)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim = fade_anim
        fade_anim.start()

        self._tick_timer.start()

    def animate_reposition(self, target_pos: QPoint) -> None:
        """Slides card vertically when lower notifications dismiss."""
        if self._is_closing or self.pos() == target_pos:
            return
        self._animate_pos(self.pos(), target_pos, 160, QEasingCurve.Type.OutQuad)

    def _on_tick(self) -> None:
        self._remaining_ms = max(0, self._remaining_ms - 50)
        self.progress_bar.setValue(self._remaining_ms)
        if self._remaining_ms <= 0:
            self.dismiss()

    def dismiss(self) -> None:
        """Slides out softly and fades opacity before closing."""
        if self._is_closing:
            return
        self._is_closing = True
        self._tick_timer.stop()

        if not self.isVisible():
            self._finalize_close()
            return

        if self._pos_anim is not None:
            self._pos_anim.stop()
        if self._fade_anim is not None:
            self._fade_anim.stop()
        if self._exit_group is not None:
            self._exit_group.stop()

        cur_pos = self.pos()
        end_pos = QPoint(cur_pos.x() + 20, cur_pos.y())
        group = QParallelAnimationGroup(self)

        pos_anim = QPropertyAnimation(self, b"pos", group)
        pos_anim.setDuration(180)
        pos_anim.setStartValue(cur_pos)
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        fade_anim = QPropertyAnimation(self, b"windowOpacity", group)
        fade_anim.setDuration(180)
        fade_anim.setStartValue(self.windowOpacity())
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)
        group.finished.connect(self._finalize_close)
        self._exit_group = group
        group.start()

    def _finalize_close(self) -> None:
        self.hide()
        self.dismissed.emit(self)
        self.deleteLater()

    def enterEvent(self, event: Any) -> None:  # noqa: N802
        if self._tick_timer.isActive() and not self._is_closing:
            self._tick_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        if not self._is_closing:
            self._remaining_ms = max(self._remaining_ms, 1200)
            self._tick_timer.start()
        super().leaveEvent(event)


class DesktopNotificationManager(QObject):
    """Stacks and positions DesktopNotificationToast cards on the primary screen."""

    MARGIN_X = 18
    MARGIN_Y = 18
    STACK_SPACING = 10
    MAX_VISIBLE = 3

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active: list[DesktopNotificationToast] = []

    def show_notification(
        self,
        title: str,
        message: str,
        duration_ms: int = 3500,
        level: str = "info",
    ) -> DesktopNotificationToast:
        while len(self._active) >= self.MAX_VISIBLE:
            oldest = self._active.pop(0)
            oldest.dismiss()

        toast = DesktopNotificationToast(
            title=title,
            message=message,
            duration_ms=duration_ms,
            level=level,
        )
        self._active.append(toast)
        toast.dismissed.connect(self._on_dismissed)

        positions = self._compute_positions()
        for idx, card in enumerate(self._active):
            if card is toast:
                card.play_enter(positions[idx])
            else:
                card.animate_reposition(positions[idx])
        return toast

    def clear_all(self) -> None:
        for card in list(self._active):
            card.dismiss()
        self._active.clear()

    def _screen_geometry(self) -> QRect:
        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return QRect(0, 0, 1280, 720)

    def _compute_positions(self) -> list[QPoint]:
        geo = self._screen_geometry()
        positions: list[QPoint] = []
        y_cursor = geo.y() + geo.height() - self.MARGIN_Y
        for card in reversed(self._active):
            card.adjustSize()
            y_cursor -= card.height()
            x = geo.x() + geo.width() - card.width() - self.MARGIN_X
            positions.append(QPoint(max(geo.x() + 12, x), max(geo.y() + 12, y_cursor)))
            y_cursor -= self.STACK_SPACING
        positions.reverse()
        return positions

    def _on_dismissed(self, closed_card: Any) -> None:
        if closed_card in self._active:
            self._active.remove(closed_card)
        if not self._active:
            return
        positions = self._compute_positions()
        for idx, card in enumerate(self._active):
            card.animate_reposition(positions[idx])
