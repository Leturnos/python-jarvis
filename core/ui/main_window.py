from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtGui import QCloseEvent
from qfluentwidgets import SplitTitleBarWindow

from core.ui.widgets.status_card import StatusCardWidget

class MainWindow(SplitTitleBarWindow):
    def __init__(self, ui_adapter):
        super().__init__()
        self.setWindowTitle("Jarvis Dashboard")
        self.resize(500, 350)
        
        self.status_card = StatusCardWidget(ui_adapter.wakeword_name, self)
        
        layout = QVBoxLayout(self.windowEffect)
        layout.setContentsMargins(20, 50, 20, 20)  # Top margin for title bar
        layout.addWidget(self.status_card)
        
        ui_adapter.visual_state_updated.connect(self.status_card.update_from_snapshot)

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()
