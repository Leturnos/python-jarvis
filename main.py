import time
import os
import numpy as np
import threading
import queue
import sys
import ctypes
import win32gui
import win32con
import pythoncom
import difflib
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS

from core.logger_config import logger
from core.config import config
from core.automator import WarpAutomator
from core.dispatcher import ActionDispatcher
from core.audio_engine import get_audio_stream, load_wakeword_model, safe_reset_audio
from core.stt_engine import stt_engine
from core.llm_agent import llm_agent
from core.ui import JarvisUI
from core.notifications import JarvisNotifier
from core.tray import JarvisTray
from core.utils import normalize_text
from core.command_palette import CommandPalette
from core.worker import command_worker
from core.monitor import MemoryMonitor
from core.state import state_manager, JarvisState
from core.job_queue import Job, JobType
from core.controller import JarvisController

from core.keyring_manager import KeyringManager

def main():
    app_title = "Jarvis AI Assistant"
    ctypes.windll.kernel32.SetConsoleTitleW(app_title)

    # Transparent migration of the API key from .env to Keyring on startup
    api_key = KeyringManager.get_secret("python-jarvis", "GEMINI_API_KEY")
    env_key = os.getenv("GEMINI_API_KEY")
    
    if env_key and (not api_key or env_key != api_key):
        logger.info("Migrating GEMINI_API_KEY from .env to secure Keyring.")
        KeyringManager.set_secret("python-jarvis", "GEMINI_API_KEY", env_key)
        logger.info("Security tip: You can now remove GEMINI_API_KEY from your .env file.")
    elif not api_key and not env_key:
        logger.error("ERROR: GEMINI_API_KEY not found in Keyring or .env!")
        print("\n[!] Error: API Key not configured.")
        print("[!] Please set GEMINI_API_KEY in your .env file to start the automatic migration.")
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
    
    def on_stop():
        stop_event.set()

    automator = WarpAutomator(config)
    pa, stream = get_audio_stream()
    dispatcher = ActionDispatcher(config, automator, stream)
    model, loaded_names = load_wakeword_model()
    
    if not model:
        logger.error("Failed to load any wakeword models. Exiting.")
        sys.exit(1)
        
    ui = JarvisUI(loaded_names)
    notifier = JarvisNotifier()
    tray = JarvisTray(on_stop_callback=on_stop, start_minimized=is_minimized, notifier=notifier)
    
    # Initialize Command Palette
    palette = CommandPalette(dispatcher)
    palette.start_background_loop()
    
    worker_thread = threading.Thread(
        target=command_worker, 
        args=(task_queue, dispatcher, notifier, stop_event, worker_busy),
        daemon=True
    )
    worker_thread.start()
    
    tray.start()
    
    memory_monitor = MemoryMonitor(interval_seconds=60, threshold_mb=800)
    memory_monitor.start()

    # Orchestration layer
    controller = JarvisController(
        config=config,
        automator=automator,
        dispatcher=dispatcher,
        model=model,
        loaded_names=loaded_names,
        ui=ui,
        tray=tray,
        task_queue=task_queue,
        stop_event=stop_event,
        pa=pa,
        stream=stream
    )

    try:
        controller.start()
    finally:
        logger.info("Cleaning up bootstrap layer...")
        if 'memory_monitor' in locals():
            memory_monitor.stop()
        stop_event.set()
        tray.stop()
        logger.info("Jarvis stopped.")

if __name__ == "__main__":
    main()