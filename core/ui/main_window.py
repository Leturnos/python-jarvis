from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from core.ui.widgets.status_card import StatusCardWidget


class MainWindow(QMainWindow):
    minimized_to_tray = Signal()

    def __init__(self, ui_adapter):
        super().__init__()
        self.setWindowTitle("Jarvis Dashboard")
        self.resize(500, 350)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.status_card = StatusCardWidget(ui_adapter.wakeword_name)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self.status_card)

        ui_adapter.visual_state_updated.connect(self.status_card.update_from_snapshot)

    def closeEvent(self, event: QCloseEvent):  # noqa: N802
        event.ignore()
        self.hide()
        self.minimized_to_tray.emit()
