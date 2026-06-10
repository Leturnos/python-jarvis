import os
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon
from qfluentwidgets import Theme, setTheme

from core.ai.llm_agent import llm_agent
from core.infra.config import config, reload_config
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.llm import LiteLLMProvider
from core.runtime.state import JarvisState, state_manager
from core.shared.utils import (
    get_resources_dir,
    is_autostart_enabled_check,
    manage_autostart,
)
from core.ui.main_window import MainWindow


def update_yaml_active_provider(provider_name: str) -> None:
    yaml_path = "config.yaml"
    if not os.path.exists(yaml_path):
        return
    with open(yaml_path, encoding="utf-8") as f:
        lines = f.readlines()

    in_llm_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("llm:"):
            in_llm_block = True
        elif in_llm_block and stripped.startswith("active_provider:"):
            # Preserve indentation
            indent = line[: line.find("active_provider:")]
            lines[i] = f'{indent}active_provider: "{provider_name}"\n'
            break
        elif in_llm_block and line.strip() == "":
            pass
        elif (
            in_llm_block
            and not line.startswith(" ")
            and not line.startswith("active_provider:")
            and stripped != ""
        ):
            in_llm_block = False

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class QtAppController(QObject):
    provider_switch_done = Signal(bool, str)

    def __init__(self, app: QApplication, ui_adapter: Any, tray_adapter: Any) -> None:
        super().__init__()
        self.provider_switch_done.connect(self._on_provider_switch_done)
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

    def _setup_tray(self) -> None:
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

        # LLM Provider Submenu
        self.provider_menu = self.tray_menu.addMenu("LLM Provider")
        self.provider_actions = {}
        provider_labels = {
            "gemini": "Gemini",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "deepseek": "DeepSeek",
            "openrouter": "OpenRouter",
        }
        for prov in ["gemini", "openai", "anthropic", "deepseek", "openrouter"]:
            label = provider_labels.get(prov, prov.capitalize())
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, p=prov: self._switch_provider(p))
            self.provider_menu.addAction(action)
            self.provider_actions[prov] = action

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

    def _update_menu_states(self) -> None:
        """Refreshes the checkmarks in the tray menu before showing it."""
        current_state = state_manager.get_state()

        # Active vs Suspended
        is_suspended = current_state in (JarvisState.SLEEPING, JarvisState.SUSPENDED)
        is_muted = current_state == JarvisState.MUTED

        self.active_action.setChecked(not is_suspended and not is_muted)
        self.suspended_action.setChecked(is_suspended)

        # Mute durations
        def get_mute_checked(minutes: int) -> bool:
            if self.tray_adapter.mute_until == 0.0:
                return False
            remaining = self.tray_adapter.mute_until - time.time()
            return bool((minutes - 5) * 60 < remaining <= (minutes + 5) * 60)

        self.mute_30m.setChecked(get_mute_checked(30))
        self.mute_1h.setChecked(get_mute_checked(60))
        self.mute_3h.setChecked(get_mute_checked(180))

        # Autostart
        self.autostart_action.setChecked(is_autostart_enabled_check())

        # LLM Provider
        active_provider = config.get("llm", {}).get("active_provider", "gemini")
        for prov, action in self.provider_actions.items():
            action.setChecked(prov == active_provider)

    def _set_suspended(self) -> None:
        state_manager.set_state(JarvisState.SLEEPING)

    def _toggle_autostart(self) -> None:
        new_state = not is_autostart_enabled_check()
        manage_autostart(enable=new_state)

    def _switch_provider(self, provider: str) -> None:
        # Pre-check existence
        if not KeyringManager.validate_provider_key(provider):
            self.tray_icon.showMessage(
                "Jarvis",
                f"API Key for {provider} not configured.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            self._update_menu_states()
            return

        # Reload configuration dynamically in case the user modified config.yaml
        current_config = reload_config()

        # Run 1-token completion test in background
        def run_test():
            llm_config = current_config.get("llm", {})
            model_name = (
                llm_config.get("providers", {}).get(provider, {}).get("model", "")
            )
            try:
                test_provider = LiteLLMProvider(provider=provider, model=model_name)
                success = test_provider.test_connection()
            except Exception as e:
                logger.error(f"Failed to create test provider or run check: {e}")
                success = False
            self.provider_switch_done.emit(success, provider)

        threading.Thread(target=run_test, daemon=True).start()

    def _on_provider_switch_done(self, success: bool, provider: str) -> None:
        if success:
            config["llm"]["active_provider"] = provider
            update_yaml_active_provider(provider)
            llm_agent.reinit_provider()
            self.tray_icon.showMessage(
                "Jarvis",
                f"IA alterada para {provider.capitalize()}.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        else:
            self.tray_icon.showMessage(
                "Jarvis",
                f"Falha na conexão ou chave inválida para {provider.capitalize()}.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
        self._update_menu_states()

    def show_window(self) -> None:
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _show_minimized_message(self) -> None:
        if hasattr(self, "tray_icon") and not self._has_shown_tray_message:
            from PySide6.QtWidgets import QSystemTrayIcon

            self.tray_icon.showMessage(
                "Jarvis",
                "O Jarvis continua rodando em segundo plano.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            self._has_shown_tray_message = True

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self.show_window()

    def quit_app(self) -> None:
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
        self.app.quit()
