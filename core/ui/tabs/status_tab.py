from typing import Any

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.ui.widgets.status_card import StatusCardWidget


class StatusTab(QWidget):
    """Tab widget for real-time status and audio metrics."""

    def __init__(self, wakeword_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status_card = StatusCardWidget(wakeword_name, self)
        layout.addWidget(self.status_card)

    def update_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.status_card.update_from_snapshot(snapshot)
