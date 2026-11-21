from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import SegmentedWidget

from core.shared.utils import get_resources_dir
from core.ui.tabs.history_tab import HistoryTab
from core.ui.tabs.plugins_tab import PluginsTab
from core.ui.tabs.settings_tab import SettingsTab
from core.ui.tabs.status_tab import StatusTab
from core.ui.widgets.title_bar import CloseTitleButton, CustomTitleBar

__all__ = ["CloseTitleButton", "CustomTitleBar", "MainWindow"]


class MainWindow(QMainWindow):
    minimized_to_tray = Signal()

    def __init__(self, ui_adapter: Any) -> None:
        super().__init__()
        self.setWindowTitle("Painel do Jarvis")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(640, 500)

        icon_path = get_resources_dir() / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        outer_widget = QWidget(self)
        self.setCentralWidget(outer_widget)
        outer_layout = QVBoxLayout(outer_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.shell_frame = QFrame(outer_widget)
        self.shell_frame.setObjectName("MainShellFrame")
        self.shell_frame.setStyleSheet(
            """
            QFrame#MainShellFrame {
                background-color: #141416;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
            }
            """
        )
        outer_layout.addWidget(self.shell_frame)

        shell_layout = QVBoxLayout(self.shell_frame)
        shell_layout.setContentsMargins(1, 1, 1, 1)
        shell_layout.setSpacing(0)

        # Custom Title Bar
        self.title_bar = CustomTitleBar(self.shell_frame)
        self.title_bar.close_clicked.connect(self.close)
        shell_layout.addWidget(self.title_bar)

        # Body Content
        body_widget = QWidget(self.shell_frame)
        layout = QVBoxLayout(body_widget)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        nav_row = QHBoxLayout()
        nav_row.addStretch(1)
        self.pivot = SegmentedWidget(body_widget)
        nav_row.addWidget(self.pivot)
        nav_row.addStretch(1)

        self.stacked_widget = QStackedWidget(body_widget)

        self.status_tab = StatusTab(
            ui_adapter.wakeword_name, body_widget, ui_adapter=ui_adapter
        )
        self.history_tab = HistoryTab(body_widget)
        self.plugins_tab = PluginsTab(body_widget)
        self.settings_tab = SettingsTab(body_widget, ui_adapter=ui_adapter)

        self._add_tab(self.status_tab, "status", "Status")
        self._add_tab(self.history_tab, "history", "Histórico")
        self._add_tab(self.plugins_tab, "plugins", "Plugins")
        self._add_tab(self.settings_tab, "settings", "Configurações")

        layout.addLayout(nav_row)
        layout.addWidget(self.stacked_widget, 1)

        shell_layout.addWidget(body_widget, 1)

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
