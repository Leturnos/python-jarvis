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
    
    logger.info(f"Jarvis is listening for {loaded_names}...")
    
    cooldown = 0
    volume_multiplier = config.get('jarvis', {}).get('volume_multiplier', 1.0)
    threshold = config.get('jarvis', {}).get('threshold', 0.4)
    cooldown_seconds = config.get('jarvis', {}).get('cooldown_seconds', 5)

    was_busy = False
    consecutive_zero_rms = 0
    MAX_ZERO_RMS_BEFORE_RESET = 30 # Approx 3 seconds of dead silence

    is_recording_command = False
    command_frames = []
    silence_start = None
    command_start_time = None

    memory_monitor = MemoryMonitor(interval_seconds=60, threshold_mb=800)
    memory_monitor.start()

    try:
        with ui.get_live() as live:
            while not stop_event.is_set():
                if worker_busy.is_set():
                    if getattr(dispatcher, 'waiting_for_auth', False):
                        ui.update(status="Aguardando Permissão...")
                    else:
                        ui.update(status="Processando...")
                    was_busy = True
                    time.sleep(0.2)
                    continue

                if was_busy:
                    was_busy = False
                    try:
                        model.reset() # Reset openwakeword state to prevent false positives from old audio
                        stream.stop_stream()
                        stream.start_stream()
                    except Exception as e:
                        logger.error(f"Error resetting stream: {e}")

                tray_muted = tray.is_muted()
                
                try:
                    now = time.time()
                    if tray_muted:
                        current_status = "MUTED/Sleeping"
                    else:
                        current_status = "Listening" if now > cooldown else "Cooldown/Executing"
                    
                    ui.update(status=current_status)

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

                    if is_recording_command:
                        ui.update(status="Gravando...")
                        command_frames.append(pcm.tobytes())
                        rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
                        
                        if rms < 15.0: # Silence threshold
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start > 1.5:
                                # Silence detected, end recording
                                is_recording_command = False
                                audio_bytes = b"".join(command_frames)
                                worker_busy.set()
                                task_queue.put(('llm_dynamic', audio_bytes))
                        else:
                            silence_start = None
                            
                        if time.time() - command_start_time > 10.0:
                            # Max timeout
                            is_recording_command = False
                            audio_bytes = b"".join(command_frames)
                            worker_busy.set()
                            task_queue.put(('llm_dynamic', audio_bytes))
                            
                        continue # Pula o processamento do openwakeword enquanto grava comando

                    # Prediction
                    highest_score = 0.0
                    detected_wakeword = None
                    
                    if not tray_muted:
                        rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
                        
                        if rms > 20: 
                            prediction = model.predict(pcm)
                            
                            # Find the wakeword with the highest score
                            for model_key, score in prediction.items():
                                if score > highest_score:
                                    highest_score = float(score)
                                    detected_wakeword = model_key
                                    
                            if highest_score > 0.1:
                                logger.debug(f"Prediction debug (RMS: {rms:.1f}): {prediction}")
                        else:
                            highest_score = 0.0
                    
                    ui.update(score=highest_score)

                    if not tray_muted and highest_score > threshold and now > cooldown:
                        # Extract base wakeword name from model key (openwakeword attaches prefix/suffix sometimes)
                        ww_name_clean = next((n for n in loaded_names if n in detected_wakeword), detected_wakeword)
                        
                        logger.info(f"Wake word '{ww_name_clean}' detected! (Score: {highest_score:.2f})")
                        ui.update(status=f"Detected: {ww_name_clean}", score=highest_score)
                        
                        if ww_name_clean == 'hey_jarvis':
                            automator.speak("Sim?")
                            is_recording_command = True
                            command_frames = []
                            silence_start = None
                            command_start_time = time.time()
                            ui.update(status="Gravando...")
                            continue 
                        else:
                            worker_busy.set()
                            automator.speak("Sim?")
                            task_queue.put((ww_name_clean, highest_score))
                        
                        cooldown = time.time() + cooldown_seconds
                        logger.debug(f"Cooldown set until {cooldown}")
                        
                    elif tray_muted and highest_score > 0.4: 
                         logger.info(f"Wake word detected but Jarvis is MUTED. (Score: {highest_score:.2f})")
                         cooldown = time.time() + cooldown_seconds
                        
                except Exception as e:
                    if not stop_event.is_set():
                        logger.error(f"Unexpected error in loop: {e}")
                        ui.update(status="Loop Error")
                        time.sleep(1)
                    else:
                        break

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