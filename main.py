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
from core.audio_engine import get_audio_stream, load_wakeword_model, record_command_audio
from core.stt_engine import stt_engine
from core.llm_agent import llm_agent
from core.ui import JarvisUI
from core.notifications import JarvisNotifier
from core.tray import JarvisTray
from core.utils import normalize_text

def command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy):
    """Worker thread that executes commands from the queue."""
    pythoncom.CoInitialize()
    logger.info("Command worker thread initialized.")
    
    while not stop_event.is_set():
        try:
            task_data = task_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        try:
            task_type, payload = task_data
            
            if task_type == 'llm_dynamic':
                audio_bytes = payload
                notifier.notify("Jarvis", "Processando áudio...")
                
                # Check for silence to prevent Whisper from hanging
                pcm = np.frombuffer(audio_bytes, dtype=np.int16)
                if len(pcm) == 0 or np.max(np.abs(pcm)) < 50:
                    logger.warning("Áudio silencioso detectado. Pulando STT para evitar travamento.")
                    dispatcher.automator.speak("Desculpe, não ouvi nada.")
                    continue
                
                # 1. STT
                text = stt_engine.transcribe(audio_bytes)
                if not text:
                    dispatcher.automator.speak("Desculpe, não entendi.")
                    continue
                    
                notifier.notify("Jarvis", f"Entendi: '{text}'.")
                
                # 2. Preparation
                wakewords_config = config.get('wakewords', {})
                available_commands = [k for k in wakewords_config.keys() if k != 'hey_jarvis']
                normalized = normalize_text(text)
                
                # 3. Stage 1: Exact Match
                if normalized in available_commands:
                    logger.info(f"Exact match found: {normalized}")
                    dispatcher.handle(normalized)
                    continue
                
                # 4. Stage 2: Fuzzy Match (difflib)
                matches = difflib.get_close_matches(normalized, available_commands, n=1, cutoff=0.7)
                if matches:
                    match = matches[0]
                    logger.info(f"Fuzzy match found: {match} for {normalized}")
                    dispatcher.handle(match)
                    continue

                # 5. Stage 3: LLM Fallback (Gemini)
                notifier.notify("Jarvis", "Pensando...")
                action_json = llm_agent.process_instruction(text, context_commands=available_commands)
                
                if not action_json:
                    dispatcher.automator.speak("Erro ao processar instrução.")
                    continue
                    
                # 6. Dispatch
                dispatcher.handle_dynamic(action_json)
                
            else:
                wakeword_name = task_type
                score = payload
                logger.info(f"Worker starting execution for '{wakeword_name}' (Score: {score:.2f})")
                notifier.notify("Jarvis", f"Comando '{wakeword_name}' detectado! (Score: {score:.2f})")
                dispatcher.handle(wakeword_name)
            
        except Exception as e:
            logger.error(f"Error in command worker: {e}")
        finally:
            task_queue.task_done()
            worker_busy.clear()
            logger.info("Worker finished task and cleared busy flag.")

            pythoncom.CoUninitialize()
            logger.info("Command worker thread stopped.")
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

    try:
        with ui.get_live() as live:
            while not stop_event.is_set():
                if worker_busy.is_set():
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

                        ui.update(volume=pcm)

                    except Exception as e:
                        if stop_event.is_set():
                            break
                        logger.error(f"Microphone stream error: {e}. Attempting to reconnect...")
                        ui.update(status="Stream Error")
                        try:
                            stream.stop_stream()
                            stream.close()
                        except:
                            pass
                        time.sleep(2)
                        _, stream = get_audio_stream()
                        continue

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
                        
                        worker_busy.set()
                        if ww_name_clean == 'hey_jarvis':
                            ui.update(status="Gravando...")
                            automator.speak("Sim?")
                            audio_bytes = record_command_audio(stream)
                            task_queue.put(('llm_dynamic', audio_bytes))
                        else:
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
