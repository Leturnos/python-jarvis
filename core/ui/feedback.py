"""Unified Obsidian feedback toasts and UI text formatters."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
}

_PROACTIVITY_DISPLAY_NAMES: dict[str, str] = {
    "objective": "Objetiva",
    "proactive": "Proativa",
}


@dataclass(frozen=True)
class SeverityStyle:
    """Visual tokens and default timing for a toast severity level."""

    accent_hex: str
    badge_bg_rgba: str
    icon_glyph: str
    default_duration_ms: int


TOAST_SEVERITY_STYLES: dict[str, SeverityStyle] = {
    "info": SeverityStyle(
        accent_hex="#4cc2ff",
        badge_bg_rgba="rgba(76, 194, 255, 0.16)",
        icon_glyph="i",
        default_duration_ms=2800,
    ),
    "success": SeverityStyle(
        accent_hex="#2ecc71",
        badge_bg_rgba="rgba(46, 204, 113, 0.16)",
        icon_glyph="✓",
        default_duration_ms=3200,
    ),
    "warning": SeverityStyle(
        accent_hex="#f39c12",
        badge_bg_rgba="rgba(243, 156, 18, 0.16)",
        icon_glyph="!",
        default_duration_ms=4500,
    ),
    "error": SeverityStyle(
        accent_hex="#ff3b5c",
        badge_bg_rgba="rgba(255, 59, 92, 0.16)",
        icon_glyph="✕",
        default_duration_ms=5500,
    ),
}


def format_provider_name(provider: str) -> str:
    """Returns canonical brand casing for supported LLM providers."""
    clean = str(provider or "").strip().lower()
    if not clean:
        return ""
    return _PROVIDER_DISPLAY_NAMES.get(clean, clean.capitalize())


def format_proactivity_label(proactivity: str) -> str:
    """Returns user-facing Portuguese label for AI proactivity level."""
    clean = str(proactivity or "").strip().lower()
    return _PROACTIVITY_DISPLAY_NAMES.get(clean, clean.capitalize())


def get_severity_style(level: str) -> SeverityStyle:
    """Resolves visual style tokens for a given severity key."""
    return TOAST_SEVERITY_STYLES.get(level.lower(), TOAST_SEVERITY_STYLES["info"])


def build_obsidian_card_qss(
    object_name: str,
    accent_hex: str,
    border_radius: int = 10,
    bg_rgba: str = "rgba(24, 25, 32, 246)",
) -> str:
    """Builds an isolated Obsidian Glass stylesheet resistant to global qdarktheme rules."""
    return f"""
        QFrame#{object_name} {{
            background-color: {bg_rgba};
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-left: 4px solid {accent_hex};
            border-radius: {border_radius}px;
            padding: 0px;
        }}
        QFrame#{object_name} QLabel {{
            background: transparent;
            border: none;
        }}
    """


class JarvisToast(QFrame):
    """Animated Obsidian Glass toast anchored inside a Jarvis parent window."""

    dismissed = Signal(object)

    def __init__(
        self,
        level: str,
        title: str,
        content: str,
        parent: QWidget,
        duration_ms: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.level = level.lower()
        self.style_spec = get_severity_style(self.level)
        self.duration_ms = (
            duration_ms
            if duration_ms is not None
            else self.style_spec.default_duration_ms
        )
        self._remaining_ms = max(0, int(self.duration_ms))
        self._is_closing = False
        self._is_hovered = False
        self._pos_anim: QPropertyAnimation | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._exit_group: QParallelAnimationGroup | None = None

        self.setObjectName("JarvisToastFrame")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            build_obsidian_card_qss(
                "JarvisToastFrame",
                self.style_spec.accent_hex,
                border_radius=10,
            )
        )

        max_w = max(280, min(470, parent.width() - 32))
        min_w = min(310, max_w)
        self.setMinimumWidth(min_w)
        self.setMaximumWidth(max_w)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(12, 10, 10, 10)
        root_layout.setSpacing(10)

        self.icon_badge = QLabel(self.style_spec.icon_glyph, self)
        self.icon_badge.setFixedSize(22, 22)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet(
            f"""
            QLabel {{
                background-color: {self.style_spec.badge_bg_rgba};
                color: {self.style_spec.accent_hex};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        root_layout.addWidget(self.icon_badge, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.title_label = QLabel(title, self)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "color: #ffffff; font-family: 'Segoe UI', sans-serif; "
            "font-size: 12.5px; font-weight: 700;"
        )
        text_col.addWidget(self.title_label)

        self.content_label = QLabel(content, self)
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet(
            "color: #c6c7d4; font-family: 'Segoe UI', sans-serif; "
            "font-size: 12px; font-weight: 400;"
        )
        self.content_label.setVisible(bool(content.strip()))
        text_col.addWidget(self.content_label)

        root_layout.addLayout(text_col, 1)

        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Fechar aviso")
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
        root_layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.dismiss)

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
        """Slides upward and fades in smoothly to the target position."""
        if self._is_closing:
            return
        start_pos = QPoint(target_pos.x(), target_pos.y() + 14)
        self.move(start_pos)
        self.show()
        self.raise_()

        self._animate_pos(start_pos, target_pos, 200, QEasingCurve.Type.OutCubic)

        if self._fade_anim is not None:
            self._fade_anim.stop()
        fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        fade_anim.setDuration(200)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim = fade_anim
        fade_anim.start()

        if self.duration_ms > 0:
            self._auto_timer.start(self.duration_ms)

    def animate_reposition(self, target_pos: QPoint) -> None:
        """Smoothly slides toast when another stacked toast dismisses."""
        if self._is_closing or self.pos() == target_pos:
            return
        self._animate_pos(self.pos(), target_pos, 160, QEasingCurve.Type.OutQuad)

    def dismiss(self) -> None:
        """Slides downward and fades out before releasing widget resources."""
        if self._is_closing:
            return
        self._is_closing = True
        self._auto_timer.stop()

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
        end_pos = QPoint(cur_pos.x(), cur_pos.y() + 12)
        group = QParallelAnimationGroup(self)

        pos_anim = QPropertyAnimation(self, b"pos", group)
        pos_anim.setDuration(180)
        pos_anim.setStartValue(cur_pos)
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", group)
        fade_anim.setDuration(180)
        fade_anim.setStartValue(self._opacity_effect.opacity())
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
        self._is_hovered = True
        if self._auto_timer.isActive() and not self._is_closing:
            rem = self._auto_timer.remainingTime()
            if rem >= 0:
                self._remaining_ms = rem
            self._auto_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        self._is_hovered = False
        if not self._is_closing and self.duration_ms > 0:
            self._auto_timer.start(max(self._remaining_ms, 1400))
        super().leaveEvent(event)


class JarvisToastManager(QObject):
    """Positions and stacks JarvisToast instances centered at the bottom of each window."""

    BOTTOM_MARGIN = 16
    STACK_SPACING = 8
    MAX_VISIBLE = 3

    def __init__(self) -> None:
        super().__init__()
        self._toasts_by_host: weakref.WeakKeyDictionary[QWidget, list[JarvisToast]] = (
            weakref.WeakKeyDictionary()
        )

    def show(
        self,
        level: str,
        title: str,
        content: str,
        parent: QWidget,
        duration: int | None = None,
    ) -> JarvisToast:
        host = parent.window() if parent.window() is not None else parent
        bucket = self._toasts_by_host.get(host)
        if bucket is None:
            bucket = []
            self._toasts_by_host[host] = bucket
            host.installEventFilter(self)

        while len(bucket) >= self.MAX_VISIBLE:
            oldest = bucket.pop(0)
            oldest.dismiss()

        toast = JarvisToast(level, title, content, parent=host, duration_ms=duration)
        bucket.append(toast)
        host_ref = weakref.ref(host)
        toast.dismissed.connect(
            lambda closed_toast: self._on_dismissed(host_ref(), closed_toast)
        )

        positions = self._compute_positions(host, bucket)
        for idx, item in enumerate(bucket):
            if item is toast:
                item.play_enter(positions[idx])
            else:
                item.animate_reposition(positions[idx])
        return toast

    def _compute_positions(
        self, host: QWidget, toasts: list[JarvisToast]
    ) -> list[QPoint]:
        positions: list[QPoint] = []
        y_cursor = host.height() - self.BOTTOM_MARGIN
        for toast in reversed(toasts):
            toast.adjustSize()
            y_cursor -= toast.height()
            x = max(8, (host.width() - toast.width()) // 2)
            positions.append(QPoint(x, max(48, y_cursor)))
            y_cursor -= self.STACK_SPACING
        positions.reverse()
        return positions

    def _on_dismissed(self, host: QWidget | None, closed_toast: Any) -> None:
        if host is None:
            return
        bucket = self._toasts_by_host.get(host)
        if not bucket:
            return
        if closed_toast in bucket:
            bucket.remove(closed_toast)
        if not bucket:
            return
        positions = self._compute_positions(host, bucket)
        for idx, item in enumerate(bucket):
            item.animate_reposition(positions[idx])

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if isinstance(watched, QWidget) and event.type() == QEvent.Type.Resize:
            bucket = self._toasts_by_host.get(watched)
            if bucket:
                positions = self._compute_positions(watched, bucket)
                for idx, item in enumerate(bucket):
                    item.move(positions[idx])
        return super().eventFilter(watched, event)


_toast_manager: JarvisToastManager | None = None


def _get_toast_manager() -> JarvisToastManager:
    global _toast_manager
    if _toast_manager is None:
        _toast_manager = JarvisToastManager()
    return _toast_manager


def show_toast(
    level: str,
    title: str,
    content: str,
    parent: QWidget | None = None,
    duration: int | None = None,
) -> JarvisToast | None:
    """Shows an animated Obsidian toast anchored to the top-level window of parent."""
    if parent is None:
        return None
    return _get_toast_manager().show(
        level=level,
        title=title,
        content=content,
        parent=parent,
        duration=duration,
    )


def show_info(
    title: str,
    content: str,
    parent: QWidget | None = None,
    duration: int | None = None,
) -> JarvisToast | None:
    """Shows an info-level JarvisToast."""
    return show_toast("info", title, content, parent=parent, duration=duration)


def show_success(
    title: str,
    content: str,
    parent: QWidget | None = None,
    duration: int | None = None,
) -> JarvisToast | None:
    """Shows a success-level JarvisToast."""
    return show_toast("success", title, content, parent=parent, duration=duration)


def show_warning(
    title: str,
    content: str,
    parent: QWidget | None = None,
    duration: int | None = None,
) -> JarvisToast | None:
    """Shows a warning-level JarvisToast."""
    return show_toast("warning", title, content, parent=parent, duration=duration)


def show_error(
    title: str,
    content: str,
    parent: QWidget | None = None,
    duration: int | None = None,
) -> JarvisToast | None:
    """Shows an error-level JarvisToast."""
    return show_toast("error", title, content, parent=parent, duration=duration)
