import os
from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from qfluentwidgets import setTheme, Theme

from core.ui.main_window import MainWindow

class QtAppController(QObject):
    def __init__(self, app: QApplication, ui_adapter, tray_adapter):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.tray_adapter = tray_adapter
        
        setTheme(Theme.DARK)
        
        self.main_window = MainWindow(ui_adapter)
        
        # Load Stylesheet
        qss_path = os.path.abspath("resources/styles.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.app.setStyleSheet(f.read())
        
        self._setup_tray()

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.abspath("resources/icon.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.main_window.style().standardIcon(QSystemTrayIcon.StandardPixmap.SP_ComputerIcon))
            
        tray_menu = QMenu()
        
        show_action = QAction("Show Dashboard", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        mute_30 = QAction("Mute 30 min", self)
        mute_30.triggered.connect(lambda: self.tray_adapter.set_mute(30))
        tray_menu.addAction(mute_30)
        
        unmute = QAction("Resume (Unmute)", self)
        unmute.triggered.connect(lambda: self.tray_adapter.set_mute(0))
        tray_menu.addAction(unmute)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self.show_window()

    def quit_app(self):
        self.tray_icon.hide()
        self.app.quit()
