import ctypes
import os
import queue
import sys
import threading
import time

import win32con
import win32gui
from win32api import GetLastError
from win32event import CreateMutex
from winerror import ERROR_ALREADY_EXISTS

from PySide6.QtWidgets import QApplication

from core.audio.audio_engine import (
    get_audio_stream,
    load_wakeword_model,
)
from core.controller import JarvisController
from core.execution.automator import WarpAutomator
from core.execution.dispatcher import ActionDispatcher
from core.execution.worker import command_worker
from core.infra.config import config
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.runtime.monitor import MemoryMonitor
from core.ui.adapter import JarvisTrayAdapter, JarvisUIAdapter
from core.ui.app_controller import QtAppController
from core.ui.command_palette import CommandPalette
from core.ui.notifications import JarvisNotifier


def main():
    app_title = "Jarvis AI Assistant"
    ctypes.windll.kernel32.SetConsoleTitleW(app_title)

    # Transparent migration of the API key from .env to Keyring on startup
    api_key = KeyringManager.get_secret("python-jarvis", "GEMINI_API_KEY")
    env_key = os.getenv("GEMINI_API_KEY")

    if env_key and (not api_key or env_key != api_key):
        logger.info("Migrating GEMINI_API_KEY from .env to secure Keyring.")
        KeyringManager.set_secret("python-jarvis", "GEMINI_API_KEY", env_key)
        logger.info(
            "Security tip: You can now remove GEMINI_API_KEY from your .env file."
        )
    elif not api_key and not env_key:
        logger.error("ERROR: GEMINI_API_KEY not found in Keyring or .env!")
        print("\n[!] Error: API Key not configured.")
        print(
            "[!] Please set GEMINI_API_KEY in your .env file to start the automatic migration."
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
    task_queue = queue.Queue()

    automator = WarpAutomator(config)
    pa, stream = get_audio_stream()
    dispatcher = ActionDispatcher(config, automator, stream)
    model, loaded_names = load_wakeword_model()

    if not model:
        logger.error("Failed to load any wakeword models. Exiting.")
        sys.exit(1)

    ui_adapter = JarvisUIAdapter(loaded_names)
    notifier = JarvisNotifier()
    tray_adapter = JarvisTrayAdapter(notifier=notifier)

    app = QApplication(sys.argv)
    
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

    memory_monitor = MemoryMonitor(interval_seconds=60, threshold_mb=800)
    memory_monitor.start()

    # Orchestration layer
    controller = JarvisController(
        config=config,
        automator=automator,
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

    def run_controller_safely():
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
    if "memory_monitor" in locals():
        memory_monitor.stop()
    logger.info("Jarvis stopped.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
