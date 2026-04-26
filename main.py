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
        nonlocal ignore_audio_until
        
        if new_state == JarvisState.CONFIRMING_DRY_RUN:
            # Wake up immediately for confirmation
            ignore_audio_until = 0
            logger.info("Entering Confirmation: Listening immediately.")

        if (old_state == JarvisState.EXECUTING or old_state == JarvisState.CONFIRMING_DRY_RUN) and new_state == JarvisState.IDLE:
            logger.info(f"Transição {old_state.name} -> IDLE. Resetando buffer de áudio e modelo.")
            try:
                model.reset()
                # Use the global ignore_audio_until to silence feedback
                ignore_audio_until = time.time() + 0.4
            except Exception as e:
                logger.error(f"Erro no reset pós-execução: {e}")

    state_manager.add_callback(on_state_change)
    
    logger.info(f"Jarvis is listening for {loaded_names}...")
    
    cooldown = 0
    volume_multiplier = config.get('jarvis', {}).get('volume_multiplier', 1.0)
    threshold = config.get('jarvis', {}).get('threshold', 0.4)
    cooldown_seconds = config.get('jarvis', {}).get('cooldown_seconds', 5)

    consecutive_zero_rms = 0
    MAX_ZERO_RMS_BEFORE_RESET = 30 # Approx 3 seconds of dead silence

    command_frames = []
    confirmation_frames = [] # New buffer for Yes/No
    silence_start = None
    command_start_time = None

    memory_monitor = MemoryMonitor(interval_seconds=60, threshold_mb=800)
    memory_monitor.start()

    ignore_audio_until = 0
    
    try:
        with ui.get_live() as live:
            while not stop_event.is_set():
                current_state = state_manager.get_state()
                now = time.time()
                
                # 1. ALWAYS read from the stream to prevent buffer overflow
                try:
                    audio_data = stream.read(1280, exception_on_overflow=False)
                    pcm = np.frombuffer(audio_data, dtype=np.int16)

                    if volume_multiplier != 1.0:
                        pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

                    rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
                    ui.update(volume=pcm)

                    # Update ignore window if Jarvis is speaking
                    if automator.is_speaking:
                        ignore_audio_until = now + 0.4
                        # Reset model continuously while speaking to flush history
                        model.reset()

                    # Self-healing: Check for dead silence
                    if rms < 0.1:
                        consecutive_zero_rms += 1
                    else:
                        consecutive_zero_rms = 0
                        
                    if consecutive_zero_rms > MAX_ZERO_RMS_BEFORE_RESET:
                        logger.warning("Dead silence detected! Self-healing...")
                        ui.update(status="Self-Healing...")
                        pa, stream = safe_reset_audio(pa, stream)
                        dispatcher.audio_stream = stream
                        consecutive_zero_rms = 0
                        model.reset()
                        continue

                except Exception as e:
                    if stop_event.is_set(): break
                    logger.error(f"Microphone stream error: {e}. Resetting...")
                    pa, stream = safe_reset_audio(pa, stream)
                    dispatcher.audio_stream = stream
                    time.sleep(1)
                    continue

                # 2. State-based Logic
                if now < ignore_audio_until:
                    ui.update(status="Ignoring Audio (Self-Feedback)")
                    continue

                if current_state == JarvisState.MUTED:
                    ui.update(status="MUTED/Sleeping")
                    continue

                if current_state == JarvisState.CONFIRMING_DRY_RUN:
                    ui.update(status="Aguardando Confirmação...")
                    confirmation_frames.append(pcm.tobytes())
                    
                    # Process Yes/No faster (every ~0.8s instead of 2s)
                    if len(confirmation_frames) > 10: 
                        audio_chunk = b"".join(confirmation_frames)
                        confirmation_frames = [] 
                        
                        try:
                            # NO VOLUME FILTER HERE - process everything to ensure we catch the start of speech
                            text = stt_engine.transcribe(audio_chunk)
                            norm = normalize_text(text)
                            if any(word in norm for word in ["sim", "confirma", "pode", "autorizo", "yes", "vai"]):
                                logger.info("Voice confirmation: APPROVED")
                                if dispatcher.active_dialog:
                                    dispatcher.active_dialog.approve()
                                ignore_audio_until = now + 0.3 # Minimal delay after action
                            elif any(word in norm for word in ["nao", "não", "cancela", "aborta", "no"]):
                                logger.info("Voice confirmation: REJECTED")
                                if dispatcher.active_dialog:
                                    dispatcher.active_dialog.reject()
                                ignore_audio_until = now + 0.3
                        except Exception as e:
                            logger.error(f"STT Error during confirmation: {e}")
                    continue

                if current_state in (JarvisState.THINKING, JarvisState.EXECUTING, JarvisState.ERROR):
                    status_map = {
                        JarvisState.THINKING: "Processando...",
                        JarvisState.EXECUTING: "Executando...",
                        JarvisState.ERROR: "Erro Detectado!"
                    }
                    ui.update(status=status_map.get(current_state, "Ocupado"))
                    continue

                if current_state == JarvisState.LISTENING:
                    ui.update(status="Gravando...")
                    command_frames.append(pcm.tobytes())
                    
                    # End recording conditions
                    stop_recording = False
                    if rms < 15.0: # Silence detection
                        if silence_start is None:
                            silence_start = now
                        elif now - silence_start > 1.5:
                            stop_recording = True
                    else:
                        silence_start = None
                        
                    if now - command_start_time > 10.0:
                        logger.warning("Listening timeout reached.")
                        stop_recording = True

                    if stop_recording:
                        audio_bytes = b"".join(command_frames)
                        # Atomic state change to prevent double processing
                        state_manager.set_state(JarvisState.THINKING)
                        task_queue.put(('llm_dynamic', audio_bytes))
                        command_frames = []
                        silence_start = None
                    continue

                if current_state == JarvisState.IDLE:
                    ui.update(status="Listening" if now > cooldown else "Cooldown")
                    
                    highest_score = 0.0
                    detected_wakeword = None
                    
                    if rms > 20 and now > cooldown: 
                        prediction = model.predict(pcm)
                        for model_key, score in prediction.items():
                            if score > highest_score:
                                highest_score = float(score)
                                detected_wakeword = model_key
                                
                        if highest_score > 0.1:
                            logger.debug(f"Prediction debug (RMS: {rms:.1f}): {prediction}")
                    
                    ui.update(score=highest_score)

                    if highest_score > threshold:
                        ww_name_clean = next((n for n in loaded_names if n in detected_wakeword), detected_wakeword)
                        logger.info(f"Wake word '{ww_name_clean}' detected! (Score: {highest_score:.2f})")
                        
                        if ww_name_clean == 'hey_jarvis':
                            automator.speak("Sim?")
                            state_manager.set_state(JarvisState.LISTENING)
                            command_frames = []
                            confirmation_frames = [] # Reset here too
                            silence_start = None
                            command_start_time = now
                        else:
                            automator.speak("Sim?")
                            task_queue.put((ww_name_clean, highest_score))
                            state_manager.set_state(JarvisState.EXECUTING) # Trigger executing for non-LLM
                        
                        cooldown = now + cooldown_seconds

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