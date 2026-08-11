from PySide6.QtWidgets import (
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.infra.logger_config import logger


class HistoryTab(QWidget):
    """Tab widget for viewing past command execution history."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.refresh_btn = QPushButton("Refresh History", self)
        self.refresh_btn.clicked.connect(self.load_history)
        layout.addWidget(self.refresh_btn)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Timestamp", "Command", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        self.load_history()

    def load_history(self) -> None:
        self.table.setRowCount(0)
        try:
            from core.persistence.history_db import history_manager

            rows = history_manager.get_history(limit=50)
            self.table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.table.setItem(i, 0, QTableWidgetItem(str(r[0])))
                self.table.setItem(i, 1, QTableWidgetItem(str(r[1])))
                self.table.setItem(i, 2, QTableWidgetItem(str(r[2])))
                self.table.setItem(i, 3, QTableWidgetItem(str(r[3])))
        except Exception as e:
            logger.warning(f"Failed to load execution history in UI: {e}")
