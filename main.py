import time
import numpy as np
import threading
import queue
import sys
import ctypes
import win32gui
import win32con
import pythoncom
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS

from core.logger_config import logger
from core.config import config
from core.automator import WarpAutomator
from core.audio_engine import get_audio_stream, load_wakeword_model
from core.ui import JarvisUI
from core.notifications import JarvisNotifier
from core.tray import JarvisTray

def command_worker(task_queue, automator, notifier, stop_event):
    """Worker thread that executes commands from the queue."""
    # Initialize COM for this thread to allow win32com usage
    pythoncom.CoInitialize()
    logger.info("Command worker thread initialized.")
    
    while not stop_event.is_set():
        try:
            # Wait for a task with a timeout to allow checking the stop_event
            try:
                score = task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
                
            logger.info(f"Worker starting execution for score: {score:.2f}")
            
            # Show notification
            notifier.notify("Jarvis", f"I'm on it! (Score: {score:.2f})")
            
            # Execute the heavy workflow in this thread
            automator.run_workflow()
            
            task_queue.task_done()
            logger.info("Worker finished task.")
        except Exception as e:
            logger.error(f"Error in command worker: {e}")
            
    pythoncom.CoUninitialize()
    logger.info("Command worker thread stopped.")

def main():
    # Set title to be findable by other instances
    app_title = "Jarvis AI Assistant"
    ctypes.windll.kernel32.SetConsoleTitleW(app_title)

    # Single Instance Check
    mutex_name = r"Global\JarvisAI_SingleInstance_Mutex"
    mutex = CreateMutex(None, False, mutex_name)
    if GetLastError() == ERROR_ALREADY_EXISTS:
        # If running and user tries to open again, try to show the window
        hwnd = win32gui.FindWindow(None, app_title)
        if hwnd:
            # Show if hidden and bring to front
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
        
        logger.info("Jarvis is already running. Bringing it to foreground.")
        time.sleep(1) # Give user time to see the message if they are looking at the console
        sys.exit(0)

    # Check for --minimized or --hidden flags
    is_minimized = "--minimized" in sys.argv or "--hidden" in sys.argv
    
    # Hide console immediately if starting hidden to avoid flicker
    if is_minimized:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    
    # Stop event for thread synchronization
    stop_event = threading.Event()
    task_queue = queue.Queue()
    
    def on_stop():
        stop_event.set()

    # Initialize components
    automator = WarpAutomator(config)
    model, wakeword_name = load_wakeword_model()
    pa, stream = get_audio_stream()
    ui = JarvisUI(wakeword_name)
    notifier = JarvisNotifier()
    tray = JarvisTray(on_stop_callback=on_stop, start_minimized=is_minimized, notifier=notifier)
    
    # Start Worker Thread for commands
    worker_thread = threading.Thread(
        target=command_worker, 
        args=(task_queue, automator, notifier, stop_event),
        daemon=True
    )
    worker_thread.start()
    
    # Start Tray in background
    tray.start()
    
    logger.info(f"Jarvis is listening for '{wakeword_name}'...")
    
    cooldown = 0
    volume_multiplier = config.get('volume_multiplier', 1.0)
    threshold = config.get('threshold', 0.4)
    cooldown_seconds = config.get('cooldown_seconds', 5)

    try:
        with ui.get_live() as live:
            while not stop_event.is_set():
                # Check for mute auto-resume background logic
                tray_muted = tray.is_muted()
                
                try:
                    # Update UI status
                    now = time.time()
                    if tray_muted:
                        current_status = "MUTED/Sleeping"
                    else:
                        current_status = "Listening" if now > cooldown else "Cooldown/Executing"
                    
                    ui.update(status=current_status)

                    # Read audio from microphone
                    try:
                        audio_data = stream.read(1280, exception_on_overflow=False)
                        pcm = np.frombuffer(audio_data, dtype=np.int16)

                        # Apply volume multiplier
                        if volume_multiplier != 1.0:
                            pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

                        # Update UI volume
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
                    score = 0.0
                    if not tray_muted:
                        # Call model directly without RMS filter for maximum sensitivity
                        prediction = model.predict(pcm)
                        hey_jarvis_key = next((k for k in prediction.keys() if wakeword_name in k), None)
                        if hey_jarvis_key:
                            score = float(prediction[hey_jarvis_key])
                            if score > 0.1:
                                logger.debug(f"Prediction debug: {prediction}")
                    
                    ui.update(score=score)

                    if not tray_muted and score > threshold and now > cooldown:
                        logger.info(f"Wake word detected! (Score: {score:.2f})")
                        ui.update(status="Detected!", score=score)
                        
                        # Use the internal non-blocking speak
                        automator.speak("Sim?")
                        
                        # Add task to queue
                        task_queue.put(score)
                        
                        # Cooldown still applies to avoid double detection
                        cooldown = time.time() + cooldown_seconds
                        logger.debug(f"Cooldown set until {cooldown}")
                        
                    elif tray_muted and score > 0.4: # Log only if it would have detected
                         logger.info(f"Wake word detected but Jarvis is MUTED. (Score: {score:.2f})")
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
        # Cleanup
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
