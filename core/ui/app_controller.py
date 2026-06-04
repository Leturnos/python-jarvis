import time

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon
from qfluentwidgets import Theme, setTheme

from core.runtime.state import JarvisState, state_manager
from core.shared.utils import (
    get_resources_dir,
    is_autostart_enabled_check,
    manage_autostart,
)
from core.ui.main_window import MainWindow


class QtAppController(QObject):
    def __init__(self, app: QApplication, ui_adapter, tray_adapter):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.tray_adapter = tray_adapter

        setTheme(Theme.DARK)

        self.main_window = MainWindow(ui_adapter)
        self._has_shown_tray_message = False
        self.main_window.minimized_to_tray.connect(self._show_minimized_message)

        # Load Stylesheet only on MainWindow to avoid breaking Fluent UI styles globally
        resources_dir = get_resources_dir()
        qss_path = resources_dir / "styles.qss"
        if qss_path.exists():
            with open(qss_path, encoding="utf-8") as f:
                self.main_window.setStyleSheet(f.read())

        self._setup_tray()

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        resources_dir = get_resources_dir()
        icon_path = resources_dir / "icon.ico"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(
                self.main_window.style().standardIcon(
                    QStyle.StandardPixmap.SP_ComputerIcon
                )
            )

        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self._update_menu_states)

        # Dashboard Action
        self.show_action = QAction("Show Dashboard", self)
        self.show_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(self.show_action)

        self.tray_menu.addSeparator()

        # State Actions
        self.active_action = QAction("Listening (Active)", self)
        self.active_action.setCheckable(True)
        self.active_action.triggered.connect(lambda: self.tray_adapter.set_mute(0))
        self.tray_menu.addAction(self.active_action)

        self.suspended_action = QAction("On (Suspended)", self)
        self.suspended_action.setCheckable(True)
        self.suspended_action.triggered.connect(self._set_suspended)
        self.tray_menu.addAction(self.suspended_action)

        # Disable for Submenu
        self.mute_menu = self.tray_menu.addMenu("Disable for...")

        self.mute_30m = QAction("30 min", self)
        self.mute_30m.setCheckable(True)
        self.mute_30m.triggered.connect(lambda: self.tray_adapter.set_mute(30))
        self.mute_menu.addAction(self.mute_30m)

        self.mute_1h = QAction("1 hour", self)
        self.mute_1h.setCheckable(True)
        self.mute_1h.triggered.connect(lambda: self.tray_adapter.set_mute(60))
        self.mute_menu.addAction(self.mute_1h)

        self.mute_3h = QAction("3 hours", self)
        self.mute_3h.setCheckable(True)
        self.mute_3h.triggered.connect(lambda: self.tray_adapter.set_mute(180))
        self.mute_menu.addAction(self.mute_3h)

        self.tray_menu.addSeparator()

        # Autostart Action
        self.autostart_action = QAction("Autostart", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.tray_menu.addAction(self.autostart_action)

        self.tray_menu.addSeparator()

        # Quit Action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _update_menu_states(self):
        """Refreshes the checkmarks in the tray menu before showing it."""
        current_state = state_manager.get_state()

        # Active vs Suspended
        is_suspended = current_state in (JarvisState.SLEEPING, JarvisState.SUSPENDED)
        is_muted = current_state == JarvisState.MUTED

        self.active_action.setChecked(not is_suspended and not is_muted)
        self.suspended_action.setChecked(is_suspended)

        # Mute durations
        def get_mute_checked(minutes):
            if self.tray_adapter.mute_until == 0:
                return False
            remaining = self.tray_adapter.mute_until - time.time()
            return (minutes - 5) * 60 < remaining <= (minutes + 5) * 60

        self.mute_30m.setChecked(get_mute_checked(30))
        self.mute_1h.setChecked(get_mute_checked(60))
        self.mute_3h.setChecked(get_mute_checked(180))

        # Autostart
        self.autostart_action.setChecked(is_autostart_enabled_check())

    def _set_suspended(self):
        state_manager.set_state(JarvisState.SLEEPING)

    def _toggle_autostart(self):
        new_state = not is_autostart_enabled_check()
        manage_autostart(enable=new_state)

    def show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _show_minimized_message(self):
        if hasattr(self, "tray_icon") and not self._has_shown_tray_message:
            from PySide6.QtWidgets import QSystemTrayIcon

            self.tray_icon.showMessage(
                "Jarvis",
                "O Jarvis continua rodando em segundo plano.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            self._has_shown_tray_message = True

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self.show_window()

    def quit_app(self):
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
        self.app.quit()
