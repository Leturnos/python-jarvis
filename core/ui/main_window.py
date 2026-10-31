from typing import Any

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
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


class CloseTitleButton(QPushButton):
    """Minimalist custom vector X close button inspired by FxSound."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Ocultar na bandeja")
        self._hovered = False
        self.setStyleSheet("background: transparent; border: none;")

    def enterEvent(self, event: Any) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hovered:
            painter.setBrush(QColor(255, 59, 92, 36))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 6, 6)

        pen_color = QColor("#ff5c77") if self._hovered else QColor("#ff3b5c")
        pen = QPen(pen_color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half = 4.5
        painter.drawLine(
            QPointF(cx - half, cy - half),
            QPointF(cx + half, cy + half),
        )
        painter.drawLine(
            QPointF(cx + half, cy - half),
            QPointF(cx - half, cy + half),
        )


class CustomTitleBar(QFrame):
    """Frameless custom top bar with Jarvis icon, title, drag support, and close button."""

    close_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(42)
        self._drag_pos: QPoint | None = None

        self.setStyleSheet(
            """
            QFrame#CustomTitleBar {
                background-color: #151518;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            }
            QLabel#TitleBarLabel {
                color: #ededf0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13.5px;
                font-weight: 600;
                background: transparent;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        self.icon_label = QLabel(self)
        self.icon_label.setStyleSheet("background: transparent;")
        icon_path = get_resources_dir() / "icon.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(20, 20)
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap)
                layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.title_label = QLabel("Jarvis", self)
        self.title_label.setObjectName("TitleBarLabel")
        layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self.close_btn = CloseTitleButton(self)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win is not None:
                self._drag_pos = (
                    event.globalPosition().toPoint() - win.frameGeometry().topLeft()
                )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            win = self.window()
            if win is not None:
                win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # Prevent maximize on double click
        event.accept()


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
        self.settings_tab = SettingsTab(body_widget)

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
