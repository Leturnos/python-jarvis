from threading import Event
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.infra.logger_config import logger


class SecurityDialog(QDialog):
    """PySide6 Security Authorization Modal Dialog."""

    def __init__(self, action_desc: str, parent: Optional[QDialog] = None) -> None:
        if not QApplication.instance():
            self._app = QApplication([])
        else:
            self._app = QApplication.instance()

        super().__init__(parent)
        self.action_desc = action_desc
        self.result = False
        self.confirmed_event = Event()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Jarvis - Autorização de Segurança")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.resize(520, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        label_text = f"Deseja executar a seguinte ação com risco elevado?\n\n{self.action_desc}"
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
        self.sim_btn.clicked.connect(self._on_sim)

        self.nao_btn = QPushButton("NÃO", self)
        self.nao_btn.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.nao_btn.clicked.connect(self._on_nao)

        btn_layout.addWidget(self.sim_btn)
        btn_layout.addWidget(self.nao_btn)
        layout.addLayout(btn_layout)

    def _on_sim(self) -> None:
        self.result = True
        self.confirmed_event.set()
        self.accept()

    def _on_nao(self) -> None:
        self.result = False
        self.confirmed_event.set()
        super().reject()

    def ask(self) -> bool:
        """Shows the dialog and blocks until the user responds."""
        try:
            logger.info(f"Showing PySide6 security dialog for action: {self.action_desc}")
            res = self.exec()
            self.result = (res == QDialog.DialogCode.Accepted)
        except Exception as e:
            logger.error(f"Error in SecurityDialog: {e}")
            self.result = False
        finally:
            self.confirmed_event.set()
        return self.result

    def approve(self) -> None:
        """Externally approves the dialog."""
        self.result = True
        self.confirmed_event.set()
        QTimer.singleShot(0, self.accept)

    def reject(self) -> None:
        """Externally rejects the dialog."""
        self.result = False
        self.confirmed_event.set()
        QTimer.singleShot(0, super().reject)

    def close(self) -> None:
        """Closes the dialog programmatically."""
        self._on_nao()

