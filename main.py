import time
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

def main():
    app_title = "Jarvis AI Assistant"
    ctypes.windll.kernel32.SetConsoleTitleW(app_title)

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
    
    def on_state_change(old_state, new_state, context):
        if old_state == JarvisState.EXECUTING and new_state == JarvisState.IDLE:
            logger.info("Execução finalizada. Resetando modelo de wake word.")
            try:
                model.reset()
            except:
                pass

    state_manager.add_callback(on_state_change)
    
    logger.info(f"Jarvis is listening for {loaded_names}...")
    
    cooldown = 0
    volume_multiplier = config.get('jarvis', {}).get('volume_multiplier', 1.0)
    threshold = config.get('jarvis', {}).get('threshold', 0.4)
    cooldown_seconds = config.get('jarvis', {}).get('cooldown_seconds', 5)

    consecutive_zero_rms = 0
    MAX_ZERO_RMS_BEFORE_RESET = 30 # Approx 3 seconds of dead silence

    command_frames = []
    silence_start = None
    command_start_time = None

    memory_monitor = MemoryMonitor(interval_seconds=60, threshold_mb=800)
    memory_monitor.start()

    try:
        with ui.get_live() as live:
            while not stop_event.is_set():
                current_state = state_manager.get_state()
                
                # 1. ALWAYS read from the stream to prevent buffer overflow
                try:
                    audio_data = stream.read(1280, exception_on_overflow=False)
                    pcm = np.frombuffer(audio_data, dtype=np.int16)

                    if volume_multiplier != 1.0:
                        pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

                    rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
                    ui.update(volume=pcm)

                    # Self-healing: Check for dead silence (Hardware/Driver hang)
                    if rms < 0.1: # Absolute silence, often indicates dead stream/driver
                        consecutive_zero_rms += 1
                    else:
                        consecutive_zero_rms = 0
                        
                    if consecutive_zero_rms > MAX_ZERO_RMS_BEFORE_RESET:
                        logger.warning("Dead silence detected! Microphone might be hung. Triggering self-healing...")
                        ui.update(status="Self-Healing...")
                        pa, stream = safe_reset_audio(pa, stream)
                        dispatcher.audio_stream = stream
                        consecutive_zero_rms = 0
                        model.reset()
                        continue

                except Exception as e:
                    if stop_event.is_set():
                        break
                    logger.error(f"Microphone stream error: {e}. Attempting self-healing reset...")
                    ui.update(status="Resetting Audio...")
                    pa, stream = safe_reset_audio(pa, stream)
                    dispatcher.audio_stream = stream
                    time.sleep(1)
                    continue

                # 2. State-based Logic
                now = time.time()

                if current_state == JarvisState.MUTED:
                    ui.update(status="MUTED/Sleeping")
                    # Still read and discard to keep stream alive (already done above)
                    continue

                if current_state in (JarvisState.THINKING, JarvisState.CONFIRMING_DRY_RUN, JarvisState.EXECUTING, JarvisState.ERROR):
                    status_map = {
                        JarvisState.THINKING: "Processando...",
                        JarvisState.CONFIRMING_DRY_RUN: "Aguardando Permissão...",
                        JarvisState.EXECUTING: "Executando...",
                        JarvisState.ERROR: "Erro Detectado!"
                    }
                    ui.update(status=status_map.get(current_state, "Ocupado"))
                    # Continue reading but skip wakeword prediction
                    continue

                if current_state == JarvisState.LISTENING:
                    ui.update(status="Gravando...")
                    command_frames.append(pcm.tobytes())
                    
                    # Silence detection to end recording
                    if rms < 15.0: # Silence threshold
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > 1.5:
                            # Silence detected, end recording
                            audio_bytes = b"".join(command_frames)
                            task_queue.put(('llm_dynamic', audio_bytes))
                            # state_manager.set_state(JarvisState.THINKING) # Worker handles this
                    else:
                        silence_start = None
                        
                    # Timeout detection
                    if time.time() - command_start_time > 10.0:
                        logger.warning("Listening timeout reached.")
                        audio_bytes = b"".join(command_frames)
                        task_queue.put(('llm_dynamic', audio_bytes))
                    
                    continue

                if current_state == JarvisState.IDLE:
                    ui.update(status="Listening" if now > cooldown else "Cooldown")
                    
                    # Wake word prediction
                    highest_score = 0.0
                    detected_wakeword = None
                    
                    if rms > 20: 
                        prediction = model.predict(pcm)
                        for model_key, score in prediction.items():
                            if score > highest_score:
                                highest_score = float(score)
                                detected_wakeword = model_key
                                
                        if highest_score > 0.1:
                            logger.debug(f"Prediction debug (RMS: {rms:.1f}): {prediction}")
                    
                    ui.update(score=highest_score)

                    if highest_score > threshold and now > cooldown:
                        ww_name_clean = next((n for n in loaded_names if n in detected_wakeword), detected_wakeword)
                        logger.info(f"Wake word '{ww_name_clean}' detected! (Score: {highest_score:.2f})")
                        
                        if ww_name_clean == 'hey_jarvis':
                            automator.speak("Sim?")
                            state_manager.set_state(JarvisState.LISTENING)
                            command_frames = []
                            silence_start = None
                            command_start_time = time.time()
                        else:
                            automator.speak("Sim?")
                            task_queue.put((ww_name_clean, highest_score))
                        
                        cooldown = time.time() + cooldown_seconds

    except KeyboardInterrupt:
        logger.info("Stopping Jarvis (KeyboardInterrupt)...")
    finally:
        logger.info("Cleaning up...")
        if 'memory_monitor' in locals():
            memory_monitor.stop()
        stop_event.set()
        tray.stop()
        try:
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except:
            pass
        logger.info("Jarvis stopped.")

if __name__ == "__main__":
    main()