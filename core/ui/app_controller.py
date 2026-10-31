import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import keyboard
import win32api
import win32con
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon
from qfluentwidgets import InfoBar, Theme, setTheme

from core.ai.llm_agent import llm_agent
from core.infra.config import config, reload_config, update_yaml_active_provider
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.infra.update_preferences import UpdatePreferenceManager
from core.infra.updater import ReleaseInfo, UpdateManager
from core.llm import LiteLLMProvider
from core.runtime.state import JarvisState, state_manager
from core.shared.constants import DEFAULT_PROVIDER
from core.shared.utils import (
    get_resources_dir,
    is_autostart_enabled_check,
    manage_autostart,
)
from core.ui.command_palette_qt import QtCommandPalette
from core.ui.main_window import MainWindow
from core.ui.voice_overlay import VoiceOverlayHUD


class QtAppController(QObject):
    provider_switch_done = Signal(bool, str)
    update_available_boot = Signal(object)

    def __init__(
        self,
        app: QApplication,
        ui_adapter: Any,
        tray_adapter: Any,
        stop_event: threading.Event | None = None,
        onboarding: bool = False,
        first_run: bool = False,
    ) -> None:
        super().__init__()
        self.provider_switch_done.connect(self._on_provider_switch_done)
        self.update_available_boot.connect(self._show_update_notification)
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.tray_adapter = tray_adapter
        self.stop_event = stop_event

        setTheme(Theme.DARK)

        resources_dir = get_resources_dir()
        icon_path = resources_dir / "icon.ico"
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
            self.app.setWindowIcon(app_icon)
        else:
            app_icon = None

        self.main_window = MainWindow(ui_adapter)
        if app_icon is not None:
            self.main_window.setWindowIcon(app_icon)
        self.main_window.settings_tab.restart_requested.connect(
            self.restart_application
        )
        self.main_window.settings_tab.update_restart_requested.connect(
            self.apply_update_and_restart
        )
        self.main_window.settings_tab.provider_changed.connect(
            lambda _: self._update_menu_states()
        )
        self.main_window.settings_tab.autostart_toggled.connect(
            self._on_settings_autostart_toggled
        )
        self.voice_overlay = VoiceOverlayHUD()
        self.command_palette: QtCommandPalette | None = None
        self._cp_hotkey: str = "ctrl+shift+p"
        self._cp_was_pressed: bool = False
        self._cp_poll_timer: QTimer | None = None
        ui_adapter.visual_state_updated.connect(self.voice_overlay.update_from_snapshot)

        self._has_shown_tray_message = False
        self.main_window.minimized_to_tray.connect(self._show_minimized_message)

        # Load Stylesheet only on MainWindow to avoid breaking Fluent UI styles globally
        qss_path = resources_dir / "styles.qss"
        if qss_path.exists():
            with open(qss_path, encoding="utf-8") as f:
                self.main_window.setStyleSheet(f.read())

        self._setup_tray()

        if onboarding:
            self.show_window()
            self.main_window.pivot.setCurrentItem("settings")
            self.main_window.stacked_widget.setCurrentWidget(
                self.main_window.settings_tab
            )
            active_provider = config.get("llm", {}).get("active_provider", "gemini")
            InfoBar.warning(
                "Bem-vindo ao Jarvis!",
                f"Configure sua chave de API para o provedor '{active_provider.capitalize()}' para ativar o assistente.",
                parent=self.main_window.settings_tab,
                duration=10000,
            )
        elif first_run:
            self.show_window()
            active_provider = config.get("llm", {}).get("active_provider", "gemini")
            InfoBar.success(
                "Bem-vindo ao Jarvis!",
                f"Assistente pronto para uso! Chave para '{active_provider.capitalize()}' configurada com sucesso.",
                parent=self.main_window.status_tab,
                duration=10000,
            )

        self._start_boot_update_check()

    def start_command_palette(self, dispatcher: Any) -> QtCommandPalette:
        self.command_palette = QtCommandPalette(dispatcher)

        cp_config = config.get("command_palette", {})
        hotkey = cp_config.get("key", "ctrl+shift+p")
        self._cp_hotkey = hotkey
        try:
            keyboard.add_hotkey(hotkey, self.command_palette.show)
        except Exception as e:
            logger.warning(f"Failed to register keyboard hook for {hotkey}: {e}")

        # Poll physical key state as a resilient fallback when Windows drops WH_KEYBOARD_LL hooks on boot
        self._cp_poll_timer = QTimer(self)
        self._cp_poll_timer.setInterval(60)
        self._cp_poll_timer.timeout.connect(self._poll_command_palette_hotkey)
        self._cp_poll_timer.start()

        logger.info(f"Qt Command Palette initialized. Hotkey: {hotkey}")
        return self.command_palette

    def update_command_palette_hotkey(self, new_hotkey: str) -> None:
        """Dynamically rebinds the command palette global shortcut and polling key."""
        clean = new_hotkey.strip().lower()
        if not clean or clean == getattr(self, "_cp_hotkey", ""):
            return

        old_hotkey = getattr(self, "_cp_hotkey", "")
        if old_hotkey:
            try:
                keyboard.remove_hotkey(old_hotkey)
            except Exception:
                pass
        self._cp_hotkey = clean
        try:
            if hasattr(self, "command_palette") and self.command_palette:
                keyboard.add_hotkey(clean, self.command_palette.show)
        except Exception as e:
            logger.warning(f"Failed to rebind hotkey hook for {clean}: {e}")

    def _is_physical_hotkey_pressed(self, hotkey_str: str) -> bool:
        """Checks if a key combination (e.g., ctrl+shift+p) is physically held down via Win32 API."""
        try:
            vk_map = {
                "ctrl": win32con.VK_CONTROL,
                "control": win32con.VK_CONTROL,
                "lctrl": win32con.VK_LCONTROL,
                "rctrl": win32con.VK_RCONTROL,
                "alt": win32con.VK_MENU,
                "menu": win32con.VK_MENU,
                "lalt": win32con.VK_LMENU,
                "ralt": win32con.VK_RMENU,
                "shift": win32con.VK_SHIFT,
                "lshift": win32con.VK_LSHIFT,
                "rshift": win32con.VK_RSHIFT,
                "win": win32con.VK_LWIN,
                "windows": win32con.VK_LWIN,
                "space": win32con.VK_SPACE,
                "tab": win32con.VK_TAB,
                "enter": win32con.VK_RETURN,
                "esc": win32con.VK_ESCAPE,
                "escape": win32con.VK_ESCAPE,
            }
            parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
            if not parts:
                return False

            for part in parts:
                vk = vk_map.get(part)
                if vk is None and len(part) == 1:
                    vk = ord(part.upper())
                if vk is None:
                    return False
                if not (win32api.GetAsyncKeyState(vk) & 0x8000):
                    return False
            return True
        except Exception:
            return False

    def _poll_command_palette_hotkey(self) -> None:
        if not self.command_palette:
            return
        pressed = self._is_physical_hotkey_pressed(self._cp_hotkey)
        if pressed and not self._cp_was_pressed:
            self._cp_was_pressed = True
            if not (
                self.command_palette.dialog and self.command_palette.dialog.isVisible()
            ):
                self.command_palette.show()
        elif not pressed:
            self._cp_was_pressed = False

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
        self.show_action = QAction("Exibir Painel", self)
        self.show_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(self.show_action)

        # Command Palette Action
        self.palette_action = QAction("Paleta de Comandos...", self)
        self.palette_action.triggered.connect(self._open_command_palette)
        self.tray_menu.addAction(self.palette_action)

        self.tray_menu.addSeparator()

        # State Actions
        self.active_action = QAction("Ouvindo (Ativo)", self)
        self.active_action.setCheckable(True)
        self.active_action.triggered.connect(lambda: self.tray_adapter.set_mute(0))
        self.tray_menu.addAction(self.active_action)

        self.suspended_action = QAction("Em Espera (Pausado)", self)
        self.suspended_action.setCheckable(True)
        self.suspended_action.triggered.connect(self._set_suspended)
        self.tray_menu.addAction(self.suspended_action)

        # Disable for Submenu
        self.mute_menu = self.tray_menu.addMenu("Silenciar por...")

        self.mute_30m = QAction("30 minutos", self)
        self.mute_30m.setCheckable(True)
        self.mute_30m.triggered.connect(lambda: self.tray_adapter.set_mute(30))
        self.mute_menu.addAction(self.mute_30m)

        self.mute_1h = QAction("1 hora", self)
        self.mute_1h.setCheckable(True)
        self.mute_1h.triggered.connect(lambda: self.tray_adapter.set_mute(60))
        self.mute_menu.addAction(self.mute_1h)

        self.mute_3h = QAction("3 horas", self)
        self.mute_3h.setCheckable(True)
        self.mute_3h.triggered.connect(lambda: self.tray_adapter.set_mute(180))
        self.mute_menu.addAction(self.mute_3h)

        self.tray_menu.addSeparator()

        # LLM Provider Submenu
        self.provider_menu = self.tray_menu.addMenu("Provedor de IA")
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
        self.autostart_action = QAction("Iniciar com o Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.tray_menu.addAction(self.autostart_action)

        self.tray_menu.addSeparator()

        # Quit Action
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _update_menu_states(self) -> None:
        """Refreshes the checkmarks in the tray menu before showing it."""
        current_state = state_manager.get_state()

        # Active vs Suspended
        is_suspended = current_state in (
            JarvisState.SLEEPING,
            JarvisState.SUSPENDED,
        )
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
        is_auto = is_autostart_enabled_check()
        self.autostart_action.setChecked(is_auto)
        if hasattr(self, "main_window") and hasattr(self.main_window, "settings_tab"):
            self.main_window.settings_tab.set_autostart_state(is_auto)

        # LLM Provider
        active_provider = config.get("llm", {}).get("active_provider", DEFAULT_PROVIDER)
        for prov, action in self.provider_actions.items():
            action.setChecked(prov == active_provider)

        # Command Palette Action Label
        cp_key = config.get("command_palette", {}).get("key", "ctrl+shift+p")
        formatted_hotkey = "+".join(p.strip().capitalize() for p in cp_key.split("+"))
        self.palette_action.setText(f"Paleta de Comandos ({formatted_hotkey})...")

    def _open_command_palette(self) -> None:
        if hasattr(self, "command_palette") and self.command_palette:
            self.command_palette.show()

    def _set_suspended(self) -> None:
        state_manager.set_state(JarvisState.SLEEPING)

    def _toggle_autostart(self) -> None:
        new_state = not is_autostart_enabled_check()
        manage_autostart(enable=new_state)
        self.autostart_action.setChecked(new_state)
        if hasattr(self, "main_window") and hasattr(self.main_window, "settings_tab"):
            self.main_window.settings_tab.set_autostart_state(new_state)

    def _on_settings_autostart_toggled(self, checked: bool) -> None:
        self.autostart_action.setChecked(checked)

    def _switch_provider(self, provider: str) -> None:
        # Pre-check existence
        if not KeyringManager.validate_provider_key(provider):
            self.tray_icon.showMessage(
                "Jarvis",
                f"Chave de API do {provider.capitalize()} não configurada.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            self._update_menu_states()
            return

        # Reload configuration dynamically in case the user modified config.yaml
        current_config = reload_config()

        # Run 1-token completion test in background
        def run_test() -> None:
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
            if (
                hasattr(self.main_window, "settings_tab")
                and self.main_window.settings_tab
            ):
                if provider in self.main_window.settings_tab.providers:
                    idx = self.main_window.settings_tab.providers.index(provider)
                    self.main_window.settings_tab.provider_combo.setCurrentIndex(idx)
            self.tray_icon.showMessage(
                "Jarvis",
                f"Provedor alterado para {provider.capitalize()}.",
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
        logger.info("Quitting Jarvis application from tray menu...")
        try:
            if hasattr(self, "tray_icon") and self.tray_icon:
                self.tray_icon.hide()
        except Exception:
            pass

        try:
            if self.stop_event:
                self.stop_event.set()
        except Exception:
            pass

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        try:
            if hasattr(self, "voice_overlay") and self.voice_overlay:
                self.voice_overlay.hide()
                self.voice_overlay.close()
        except Exception:
            pass

        try:
            if (
                hasattr(self, "command_palette")
                and self.command_palette
                and self.command_palette.dialog
            ):
                self.command_palette.dialog.hide()
                self.command_palette.dialog.close()
        except Exception:
            pass

        try:
            if hasattr(self, "main_window") and self.main_window:
                self.main_window.hide()
                self.main_window.close()
        except Exception:
            pass

        # Unconditionally force process termination
        os._exit(0)

    def restart_application(self) -> None:
        """Safely restarts the current Jarvis application process."""
        logger.info("Restarting Jarvis application process...")
        try:
            if hasattr(self, "tray_icon") and self.tray_icon:
                self.tray_icon.hide()
        except Exception:
            pass

        try:
            if self.stop_event:
                self.stop_event.set()
        except Exception:
            pass

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        try:
            if hasattr(self, "_cp_poll_timer") and self._cp_poll_timer:
                self._cp_poll_timer.stop()
        except Exception:
            pass

        args = [a for a in sys.argv if a != "--restart"]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, *args[1:], "--restart"]
        else:
            cmd = [sys.executable, *args, "--restart"]

        try:
            subprocess.Popen(cmd, close_fds=True)
        except Exception as e:
            logger.error(f"Failed to spawn restarted process: {e}")
            os.execv(sys.executable, [sys.executable] + sys.argv)
            return

        os._exit(0)

    def apply_update_and_restart(self, extracted_dir: Path) -> None:
        """Applies a downloaded binary update via UpdateManager and exits cleanly."""
        logger.info(f"Applying binary update from {extracted_dir} and exiting...")
        app = QApplication.instance()
        if app:
            app.processEvents()

        updater = UpdateManager()
        updater.apply_update_and_restart(
            source_dir=extracted_dir,
            exit_callback=self.quit_app,
        )

    def _start_boot_update_check(self) -> None:
        """Starts a background thread to check for updates on startup if enabled."""
        check_on_boot = config.get("updates", {}).get("check_on_boot", True)
        if not check_on_boot:
            return
        threading.Thread(target=self._run_boot_update_check, daemon=True).start()

    def _run_boot_update_check(self) -> None:
        """Runs the boot update check with interval rate-limiting and user snooze enforcement."""
        try:
            pref_mgr = UpdatePreferenceManager()
            if not pref_mgr.can_check_on_boot():
                logger.debug(
                    "Boot update check skipped: rate limited by check interval."
                )
                return

            pref_mgr.record_check()
            updater = UpdateManager()
            info = updater.check_for_updates()
            if not info or not info.has_update:
                return

            if not pref_mgr.should_notify_version(info.version):
                logger.info(
                    f"Update {info.version} available but notification suppressed by user preference."
                )
                return

            self.update_available_boot.emit(info)
        except Exception as e:
            logger.debug(f"Boot update check failed silently: {e}")

    def _show_update_notification(self, info: ReleaseInfo) -> None:
        """Shows unobtrusive tray balloon or InfoBar notification when an update is available."""
        if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                f"Jarvis - Nova Versão {info.version}",
                "Uma nova versão está disponível. Clique para abrir as configurações e atualizar.",
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
            try:
                self.tray_icon.messageClicked.connect(
                    self._on_update_tray_message_clicked
                )
            except Exception:
                pass
        elif hasattr(self, "main_window") and self.main_window.isVisible():
            InfoBar.info(
                f"Nova Versão {info.version} Disponível",
                f"{info.title}. Acesse a aba Configurações para atualizar.",
                parent=self.main_window,
                duration=10000,
            )

    def _on_update_tray_message_clicked(self) -> None:
        """Navigates to Settings tab when user clicks the update tray balloon."""
        self.show_window()
        self.main_window.pivot.setCurrentItem("settings")
        self.main_window.stacked_widget.setCurrentWidget(self.main_window.settings_tab)
