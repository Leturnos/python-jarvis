from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget

from core.ui.tabs.history_tab import HistoryTab
from core.ui.tabs.settings_tab import SettingsTab
from core.ui.tabs.status_tab import StatusTab


class MainWindow(QMainWindow):
    minimized_to_tray = Signal()

    def __init__(self, ui_adapter: Any) -> None:
        super().__init__()
        self.setWindowTitle("Painel do Jarvis")
        self.resize(640, 480)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 15, 15, 15)

        self.pivot = SegmentedWidget(self)
        self.stacked_widget = QStackedWidget(self)

        self.status_tab = StatusTab(ui_adapter.wakeword_name, self)
        self.history_tab = HistoryTab(self)
        self.settings_tab = SettingsTab(self)

        self._add_tab(self.status_tab, "status", "Status")
        self._add_tab(self.history_tab, "history", "Histórico")
        self._add_tab(self.settings_tab, "settings", "Configurações")

        layout.addWidget(self.pivot)
        layout.addWidget(self.stacked_widget)

        self.pivot.setCurrentItem("status")
        ui_adapter.visual_state_updated.connect(self._on_state_updated)

    def _add_tab(self, widget: QWidget, route_key: str, title: str) -> None:
        self.stacked_widget.addWidget(widget)
        self.pivot.addItem(
            routeKey=route_key,
            text=title,
            onClick=lambda: self.stacked_widget.setCurrentWidget(widget),
        )

    def _on_state_updated(self, snapshot: dict[str, Any]) -> None:
        self.status_tab.update_from_snapshot(snapshot)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()
        self.minimized_to_tray.emit()
