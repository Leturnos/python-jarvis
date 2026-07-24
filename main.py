import ctypes
import os
import queue
import sys
import threading
import time
from typing import Any

import qdarktheme
import win32con
import win32gui
from PySide6.QtWidgets import QApplication
from win32api import GetLastError
from win32event import CreateMutex
from winerror import ERROR_ALREADY_EXISTS

from core.audio.audio_engine import (
    get_audio_stream,
    load_wakeword_model,
)
from core.audio.tts_engine import TTSEngine
from core.controller import JarvisController
from core.execution.dispatcher import ActionDispatcher
from core.execution.plan_builder import PlanBuilder
from core.execution.step_executor import StepExecutor
from core.execution.window_manager import WindowManager
from core.execution.worker import command_worker
from core.infra.config import config
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.media.cv_matcher import TemplateMatcher
from core.media.spotify_automator import SpotifyAutomator
from core.runtime.monitor import MemoryMonitor
from core.shared.constants import Timing
from core.ui.adapter import JarvisTrayAdapter, JarvisUIAdapter
from core.ui.app_controller import QtAppController
from core.ui.command_palette import CommandPalette
from core.ui.notifications import JarvisNotifier


def qt_exception_hook(exctype: Any, value: Any, tb: Any) -> None:
    logger.error("Uncaught Qt Exception:", exc_info=(exctype, value, tb))
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = qt_exception_hook


def main() -> None:
    app_title = "Jarvis AI Assistant"
    ctypes.windll.kernel32.SetConsoleTitleW(app_title)

    Timing.load_from_config(config)

    # Transparent migration of the active LLM provider API key to Keyring on startup
    llm_config = config.get("llm", {})
    active_provider = llm_config.get("active_provider", "gemini")
    key_name = f"{active_provider.upper()}_API_KEY"

    api_key = KeyringManager.get_secret("python-jarvis", key_name)
    env_key = os.getenv(key_name)

    if env_key and (not api_key or env_key != api_key):
        logger.info(f"Migrating {key_name} from .env to secure Keyring.")
        KeyringManager.set_secret("python-jarvis", key_name, env_key)
        logger.info(f"Security tip: You can now remove {key_name} from your .env file.")
    elif not api_key and not env_key:
        logger.error(f"ERROR: {key_name} not found in Keyring or .env!")
        print(f"\n[!] Error: API Key for '{active_provider}' not configured.")
        print(
            f"[!] Please set {key_name} in your .env file to start the automatic migration."
        )
        time.sleep(5)
        sys.exit(1)

    mutex_name = r"Global\JarvisAI_SingleInstance_Mutex"
    mutex = CreateMutex(None, False, mutex_name)
    if GetLastError() == ERROR_ALREADY_EXISTS:
        hwnd = win32gui.FindWindow(None, app_title)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)

        logger.info("Jarvis is already running. Bringing it to foreground.")
        time.sleep(1)
        sys.exit(0)

    is_minimized = "--minimized" in sys.argv or "--hidden" in sys.argv

    if is_minimized:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)

    stop_event = threading.Event()
    worker_busy = threading.Event()
    task_queue: queue.Queue[Any] = queue.Queue()

    tts_engine = TTSEngine(config)
    window_manager = WindowManager()
    template_matcher = TemplateMatcher()
    spotify_automator = SpotifyAutomator(
        config, window_manager, tts_engine, template_matcher
    )
    step_executor = StepExecutor(config, window_manager, spotify_automator, tts_engine)
    plan_builder = PlanBuilder(config)

    pa, stream = get_audio_stream(config)
    dispatcher = ActionDispatcher(
        config, step_executor, tts_engine, plan_builder, stream
    )
    model, loaded_names = load_wakeword_model(config)

    if not model:
        logger.error("Failed to load any wakeword models. Exiting.")
        sys.exit(1)

    ui_adapter = JarvisUIAdapter(loaded_names)
    notifier = JarvisNotifier()
    tray_adapter = JarvisTrayAdapter(notifier=notifier)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Initialize dark theme as early as possible to avoid flash of white or bugged colors
    qdarktheme.setup_theme()

    app_controller = QtAppController(app, ui_adapter, tray_adapter)

    if not is_minimized:
        app_controller.show_window()

    # Initialize Command Palette
    palette = CommandPalette(dispatcher)
    palette.start_background_loop()

    worker_thread = threading.Thread(
        target=command_worker,
        args=(task_queue, dispatcher, notifier, stop_event, worker_busy),
        daemon=True,
    )
    worker_thread.start()

    memory_config = config.get("runtime", {}).get("memory_monitor", {})
    mem_interval = memory_config.get("interval_seconds", 60)
    mem_threshold = memory_config.get("threshold_mb", 800.0)
    memory_monitor = MemoryMonitor(
        interval_seconds=mem_interval, threshold_mb=mem_threshold
    )
    memory_monitor.start()

    # Orchestration layer
    controller = JarvisController(
        config=config,
        tts_engine=tts_engine,
        dispatcher=dispatcher,
        model=model,
        loaded_names=loaded_names,
        ui=ui_adapter,
        tray=tray_adapter,
        task_queue=task_queue,
        stop_event=stop_event,
        pa=pa,
        stream=stream,
    )

    def run_controller_safely() -> None:
        try:
            controller.start()
        except Exception as e:
            logger.exception(f"Fatal error in JarvisController thread: {e}")
        finally:
            # Tell Qt to quit if the backend crashes or stops
            app_controller.quit_app()

    controller_thread = threading.Thread(target=run_controller_safely, daemon=True)
    controller_thread.start()

    exit_code = app.exec()

    logger.info("Cleaning up bootstrap layer...")
    stop_event.set()
    tts_engine.stop()
    if "memory_monitor" in locals():
        memory_monitor.stop()
    logger.info("Jarvis stopped.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
