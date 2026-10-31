import threading
from threading import Event
from typing import Any

from PySide6.QtCore import (
    QCoreApplication,
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.utils import get_resources_dir
from core.ui.screen_position import reposition_on_screen


class SecurityDialogWidget(QDialog):
    """Frameless floating card for Security Authorization with entry/exit animations
    and configurable screen position. Does not steal keyboard focus.
    """

    def __init__(
        self,
        action_desc: str,
        parent: QDialog | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must be initialized on the main thread.")

        super().__init__(parent)
        self.action_desc = action_desc
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.remaining_seconds = self.timeout_seconds
        self._closing_animated = False
        self._entry_opacity_anim: QPropertyAnimation | None = None
        self._entry_pos_anim: QPropertyAnimation | None = None
        self._exit_opacity_anim: QPropertyAnimation | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Jarvis - Autorização de Segurança")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(480)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.card_frame = QFrame(self)
        self.card_frame.setObjectName("SecurityCardFrame")
        self._apply_card_border_color("rgba(255, 255, 255, 0.08)")
        outer_layout.addWidget(self.card_frame)

        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # 1. Header Row: Jarvis Icon + Title + Risk/Timer Badge
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.icon_label = QLabel(self.card_frame)
        icon_path = get_resources_dir() / "icon.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(18, 18)
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap)
                header_row.addWidget(self.icon_label)

        self.title_label = QLabel("Confirmação de Segurança", self.card_frame)
        self.title_label.setStyleSheet(
            "color: #f4f4f6; font-size: 13.5px; font-weight: 600; background: transparent;"
        )
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)

        self.badge_label = QLabel(
            f"⚠️ Risco Elevado • {self.remaining_seconds}s", self.card_frame
        )
        self._set_badge_style("warning")
        header_row.addWidget(self.badge_label)
        card_layout.addLayout(header_row)

        # 2. Subtitle prompt
        self.prompt_label = QLabel(
            "O Jarvis solicita permissão para executar:", self.card_frame
        )
        self.prompt_label.setStyleSheet(
            "color: #9e9ea8; font-size: 12px; background: transparent;"
        )
        card_layout.addWidget(self.prompt_label)

        # 3. Monospace Command / Action Block
        self.cmd_box = QLabel(self.action_desc, self.card_frame)
        self.cmd_box.setWordWrap(True)
        self.cmd_box.setStyleSheet(
            """
            QLabel {
                background-color: #101013;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-left: 3px solid #f39c12;
                border-radius: 6px;
                padding: 10px 12px;
                color: #ffd166;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
            """
        )
        card_layout.addWidget(self.cmd_box)

        # 4. Countdown Progress Bar
        self.countdown_bar = QProgressBar(self.card_frame)
        self.countdown_bar.setRange(0, self.timeout_seconds * 10)
        self.countdown_bar.setValue(self.timeout_seconds * 10)
        self.countdown_bar.setTextVisible(False)
        self.countdown_bar.setFixedHeight(4)
        self.countdown_bar.setStyleSheet(
            """
            QProgressBar {
                background-color: #23232b;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #f39c12;
                border-radius: 2px;
            }
            """
        )
        card_layout.addWidget(self.countdown_bar)

        # 5. Footer Row: Voice Hint + Cancelar / Autorizar Buttons (no Enter/Esc focus stealing)
        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)

        self.voice_hint_label = QLabel(
            '🎙️ Diga <b>"Sim"</b> ou <b>"Não"</b>', self.card_frame
        )
        self.voice_hint_label.setStyleSheet(
            "color: #7d7d88; font-size: 11.5px; background: transparent;"
        )
        footer_row.addWidget(self.voice_hint_label)
        footer_row.addStretch(1)

        self.nao_btn = QPushButton("Cancelar", self.card_frame)
        self.nao_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nao_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #23232b;
                color: #dcdce2;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 59, 92, 0.16);
                border-color: #ff3b5c;
                color: #ffffff;
            }
            """
        )
        self.nao_btn.clicked.connect(self.reject)

        self.sim_btn = QPushButton("Autorizar", self.card_frame)
        self.sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sim_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1084df;
            }
            """
        )
        self.sim_btn.clicked.connect(self.accept)

        footer_row.addWidget(self.nao_btn)
        footer_row.addWidget(self.sim_btn)
        card_layout.addLayout(footer_row)

        self.adjustSize()

        # Countdown timer
        self._tick_count = self.timeout_seconds * 10
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(100)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

    def _apply_card_border_color(self, border_css_color: str) -> None:
        self.card_frame.setStyleSheet(
            f"""
            QFrame#SecurityCardFrame {{
                background-color: rgba(22, 22, 26, 246);
                border: 1px solid {border_css_color};
                border-radius: 12px;
            }}
            """
        )

    def _set_badge_style(self, mode: str) -> None:
        if mode == "approved":
            self.badge_label.setStyleSheet(
                """
                background-color: rgba(46, 204, 113, 0.18);
                color: #2ecc71;
                border: 1px solid rgba(46, 204, 113, 0.45);
                border-radius: 9px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
                """
            )
        elif mode == "rejected":
            self.badge_label.setStyleSheet(
                """
                background-color: rgba(255, 59, 92, 0.18);
                color: #ff3b5c;
                border: 1px solid rgba(255, 59, 92, 0.45);
                border-radius: 9px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
                """
            )
        else:
            self.badge_label.setStyleSheet(
                """
                background-color: rgba(243, 156, 18, 0.16);
                color: #f39c12;
                border: 1px solid rgba(243, 156, 18, 0.4);
                border-radius: 9px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
                """
            )

    def _on_countdown_tick(self) -> None:
        self._tick_count = max(0, self._tick_count - 1)
        self.countdown_bar.setValue(self._tick_count)
        secs = (self._tick_count + 9) // 10
        if secs != self.remaining_seconds:
            self.remaining_seconds = secs
            self.badge_label.setText(f"⚠️ Risco Elevado • {self.remaining_seconds}s")

    def reposition_to_configured_spot(self) -> QPoint:
        pos_key = config.get("ui", {}).get("confirmation_position", "top_center")
        return reposition_on_screen(self, pos_key)

    def play_entry_animation(self) -> None:
        """Plays a subtle slide + fade-in animation at the configured screen position."""
        target_pos = self.reposition_to_configured_spot()
        start_pos = QPoint(target_pos.x(), target_pos.y() - 12)
        self.move(start_pos)
        self.setWindowOpacity(0.0)

        self._entry_opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._entry_opacity_anim.setDuration(180)
        self._entry_opacity_anim.setStartValue(0.0)
        self._entry_opacity_anim.setEndValue(1.0)
        self._entry_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._entry_pos_anim = QPropertyAnimation(self, b"pos", self)
        self._entry_pos_anim.setDuration(180)
        self._entry_pos_anim.setStartValue(start_pos)
        self._entry_pos_anim.setEndValue(target_pos)
        self._entry_pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._entry_opacity_anim.start()
        self._entry_pos_anim.start()
        self._countdown_timer.start()

    def animate_and_finish(self, accepted: bool) -> None:
        """Shows green/red visual confirmation feedback and fades out before finishing."""
        if self._closing_animated:
            return
        self._closing_animated = True
        self._countdown_timer.stop()
        self.sim_btn.setEnabled(False)
        self.nao_btn.setEnabled(False)

        if accepted:
            self._apply_card_border_color("#2ecc71")
            self._set_badge_style("approved")
            self.badge_label.setText("✔ Autorizado")
        else:
            self._apply_card_border_color("#ff3b5c")
            self._set_badge_style("rejected")
            self.badge_label.setText("✕ Cancelado")

        result_code = (
            QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
        )

        if not self.isVisible():
            self.done(result_code)
            return

        self._exit_opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._exit_opacity_anim.setDuration(190)
        self._exit_opacity_anim.setStartValue(self.windowOpacity())
        self._exit_opacity_anim.setEndValue(0.0)
        self._exit_opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._exit_opacity_anim.finished.connect(lambda: self.done(result_code))
        self._exit_opacity_anim.start()

    def accept(self) -> None:
        if self.isVisible() and not self._closing_animated:
            self.animate_and_finish(True)
        else:
            self._countdown_timer.stop()
            super().accept()

    def reject(self) -> None:
        if self.isVisible() and not self._closing_animated:
            self.animate_and_finish(False)
        else:
            self._countdown_timer.stop()
            super().reject()


class SecurityDialogManager(QObject):
    """Coordinates thread-safe execution of SecurityDialogWidget on the main Qt GUI thread."""

    show_requested = Signal(str, object, object)  # action_desc, result_box, done_event
    approve_requested = Signal()
    reject_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.show_requested.connect(self._on_show_dialog)
        self.approve_requested.connect(self._on_approve)
        self.reject_requested.connect(self._on_reject)
        self.active_dialog: SecurityDialogWidget | None = None
        self._current_result_box: dict[str, Any] | None = None
        self._current_done_event: Event | None = None

    def _on_show_dialog(
        self, action_desc: str, result_box: dict[str, Any], done_event: Event
    ) -> None:
        logger.info(f"Showing PySide6 security dialog on GUI thread for: {action_desc}")
        self._current_result_box = result_box
        self._current_done_event = done_event

        timeout_sec = int(config.get("dry_run", {}).get("timeout_seconds", 15))
        dialog = SecurityDialogWidget(action_desc, timeout_seconds=timeout_sec)
        self.active_dialog = dialog

        def on_finished(result_code: int) -> None:
            is_accepted = result_code == QDialog.DialogCode.Accepted
            result_box["result"] = is_accepted
            self.active_dialog = None
            self._current_result_box = None
            self._current_done_event = None
            # Only unblock waiting thread AFTER the result is recorded
            done_event.set()

        dialog.finished.connect(on_finished)
        dialog.reposition_to_configured_spot()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.play_entry_animation()

    def _on_approve(self) -> None:
        if self.active_dialog:
            self.active_dialog.accept()

    def _on_reject(self) -> None:
        if self.active_dialog:
            self.active_dialog.reject()

    def approve(self) -> None:
        """Thread-safe external approval (e.g. from voice controller or test)."""
        if threading.current_thread() is threading.main_thread():
            self._on_approve()
        else:
            self.approve_requested.emit()

    def reject(self) -> None:
        """Thread-safe external rejection."""
        if threading.current_thread() is threading.main_thread():
            self._on_reject()
        else:
            self.reject_requested.emit()

    def ask_authorization(self, action_desc: str, timeout: float = 45.0) -> bool:
        """Requests authorization in a thread-safe manner."""
        app = QApplication.instance()
        if app is None:
            logger.warning(
                "No QApplication instance available for security authorization."
            )
            return False

        if threading.current_thread() is threading.main_thread():
            dialog = SecurityDialogWidget(action_desc)
            self.active_dialog = dialog
            try:
                res = dialog.exec()
                return res == QDialog.DialogCode.Accepted
            finally:
                self.active_dialog = None

        result_box = {"result": False}
        done_event = Event()
        self.show_requested.emit(action_desc, result_box, done_event)
        signaled = done_event.wait(timeout=timeout)
        if not signaled:
            logger.warning(f"Security authorization timed out for: {action_desc}")
            self.reject()
            return False

        return result_box.get("result", False)


_security_dialog_manager: SecurityDialogManager | None = None


def get_security_dialog_manager() -> SecurityDialogManager | None:
    """Returns or lazily creates the singleton SecurityDialogManager on the main thread."""
    global _security_dialog_manager
    app = QApplication.instance()
    if app is None:
        return None
    if _security_dialog_manager is None:
        _security_dialog_manager = SecurityDialogManager()
    return _security_dialog_manager


def init_security_dialog_manager() -> SecurityDialogManager | None:
    """Explicit initializer to bind the manager to the main GUI thread during app bootstrap."""
    return get_security_dialog_manager()


class SecurityDialog:
    """Thread-safe handle for Security Dialog authorization.

    Does NOT create QWidget instances on secondary threads.
    """

    def __init__(self, action_desc: str, parent: Any = None) -> None:
        self.action_desc = action_desc
        self.user_result = False
        self.confirmed_event = Event()

    def ask(self, timeout: float = 45.0) -> bool:
        """Requests user confirmation.

        On the main GUI thread, executes SecurityDialogWidget directly (supporting mocks).
        On a secondary thread, delegates to SecurityDialogManager without thread affinity violations.
        """
        app = QApplication.instance()
        if app is None or threading.current_thread() is threading.main_thread():
            if app is None:
                self._app: QCoreApplication | None = QApplication([])
            try:
                logger.info(
                    f"Showing PySide6 security dialog for action: {self.action_desc}"
                )
                widget = SecurityDialogWidget(self.action_desc)
                res = widget.exec()
                self.user_result = res == QDialog.DialogCode.Accepted
            except Exception as e:
                logger.error(f"Error in SecurityDialogWidget: {e}")
                self.user_result = False
            finally:
                self.confirmed_event.set()
            return self.user_result

        manager = get_security_dialog_manager()
        if manager is None:
            self.user_result = False
            self.confirmed_event.set()
            return False

        self.user_result = manager.ask_authorization(self.action_desc, timeout=timeout)
        self.confirmed_event.set()
        return self.user_result

    def approve(self) -> None:
        """Externally approves the active dialog."""
        self.user_result = True
        manager = get_security_dialog_manager()
        if manager:
            manager.approve()

    def reject(self) -> None:
        """Externally rejects the active dialog."""
        self.user_result = False
        manager = get_security_dialog_manager()
        if manager:
            manager.reject()

    def close(self) -> bool:
        """Closes the dialog programmatically."""
        self.reject()
        self.confirmed_event.set()
        return True
