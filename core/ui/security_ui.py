import threading
from threading import Event
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.infra.logger_config import logger


class SecurityDialogWidget(QDialog):
    """PySide6 Security Authorization Modal Dialog.

    Must ONLY be instantiated and shown on the main Qt GUI thread.
    """

    def __init__(self, action_desc: str, parent: QDialog | None = None) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must be initialized on the main thread.")

        super().__init__(parent)
        self.action_desc = action_desc
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Jarvis - Autorização de Segurança")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.resize(520, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        label_text = (
            f"Deseja executar a seguinte ação com risco elevado?\n\n{self.action_desc}"
        )
        label = QLabel(label_text, self)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.sim_btn = QPushButton("SIM", self)
        self.sim_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.sim_btn.clicked.connect(self.accept)

        self.nao_btn = QPushButton("NÃO", self)
        self.nao_btn.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.nao_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.sim_btn)
        btn_layout.addWidget(self.nao_btn)
        layout.addLayout(btn_layout)


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

        dialog = SecurityDialogWidget(action_desc)
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
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
