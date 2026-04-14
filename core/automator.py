import threading
import time
import subprocess
import psutil
import pygetwindow as gw
import win32gui
import win32con
import win32process
import win32com.client
import pyautogui
import pyperclip
import queue
import pythoncom # Required for COM in multiple threads on Windows
from core.logger_config import logger

class WarpAutomator:
    def __init__(self, config):
        self.config = config
        self.warp_path = ""
        self.commands = []

        # Dedicated TTS Thread to avoid blocking and thread-safety issues
        self._speech_queue = queue.Queue()
        self._stop_tts = threading.Event()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def _tts_worker(self):
        """Dedicated worker for TTS processing using native Windows SAPI5."""
        try:
            # Initialize COM in this thread
            pythoncom.CoInitialize()
            
            # Use Dispatch directly for better stability
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            
            # Find a Portuguese voice if available
            try:
                available_voices = voice.GetVoices()
                for i in range(available_voices.Count):
                    v = available_voices.Item(i)
                    desc = v.GetDescription()
                    if "portuguese" in desc.lower() or "brazil" in desc.lower() or "maria" in desc.lower():
                        voice.Voice = v
                        logger.info(f"SAPI Voice selected: {desc}")
                        break
            except Exception as e:
                logger.debug(f"Default voice will be used: {e}")

            # SAPI Rate is -10 to 10 (0 is normal)
            voice.Rate = 2 
            voice.Volume = 100

            while not self._stop_tts.is_set():
                try:
                    # Non-blocking check for items in queue
                    text = self._speech_queue.get(timeout=0.5)
                    logger.info(f"Jarvis is speaking: '{text}'")
                    
                    # 0 = Synchronous speak (fine because we are in a dedicated worker thread)
                    voice.Speak(text, 0)
                    
                    self._speech_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"SAPI TTS error: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize SAPI5: {e}")
        finally:
            pythoncom.CoUninitialize()
            logger.info("TTS Worker thread finishing.")

    def speak(self, text):
        """Adds text to the speech queue for immediate, non-blocking playback."""
        self._speech_queue.put(text)

    def is_open(self):
        """Checks if the Warp process is running."""
        try:
            for p in psutil.process_iter(['name']):
                if p.info['name'] and "warp" in p.info['name'].lower():
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        return False

    def find_window(self):
        """Finds the Warp terminal window using PID or title matching."""
        try:
            # 1. Get all PIDs for processes named "warp"
            warp_pids = set()
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] and "warp" in p.info['name'].lower():
                    warp_pids.add(p.info['pid'])
            
            if not warp_pids:
                logger.debug("No warp PIDs found.")
                return None

            # 2. Search for a window belonging to one of these PIDs
            for w in gw.getAllWindows():
                if w._hWnd:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(w._hWnd)
                        if pid in warp_pids and w.title:
                            return w
                    except:
                        continue
        except Exception as e:
            logger.error(f"Error searching for Warp window: {e}")
                    
        # Fallback to title search
        keywords = ('warp', 'ready', 'working', 'mvp')
        for w in gw.getAllWindows():
            if w.title and any(kw in w.title.lower() for kw in keywords):
                return w
                
        return None

    def activate_window(self, win):
        """Brings the terminal window to the foreground and clicks it."""
        try:
            hwnd = win._hWnd
            logger.info(f"Activating window HWND: {hwnd}")
            
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            
            time.sleep(0.5)

            try:
                # ALT key trick to steal focus on Windows
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys('%') 
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.warning(f"Focus error: {e}")
                win.activate()

            time.sleep(0.4)
            center_x = win.left + win.width // 2
            center_y = win.top + win.height // 2
            logger.info(f"Clicking at ({center_x}, {center_y})")
            pyautogui.click(center_x, center_y)
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error(f"Error activating window: {e}")
            return False

    def type_text(self, text):
        """Types text using the clipboard to handle special characters."""
        try:
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error typing text: {e}")

    def run_workflow(self):
        """Executes the full automation workflow with window validation."""
        logger.info("Starting automation workflow...")
        
        # 1. Open Warp if not already running
        if not self.is_open():
            logger.info("Warp not open. Opening...")
            subprocess.Popen(self.warp_path)
            
            # Wait for process to appear (max 10s)
            for _ in range(20): 
                if self.is_open():
                    break
                time.sleep(0.5)
            
        # 2. Wait for the window to become available
        win = None
        for attempt in range(20): # Up to 10 seconds total
            win = self.find_window()
            if win:
                break
            time.sleep(0.5)

        if not win:
            logger.warning("Warp window not found after waiting.")
            self.speak("Não encontrei a janela do Warp.")
            return

        # 3. Activate and Validate
        logger.info(f"Found Warp window: {win.title}. Activating...")
        if self.activate_window(win):
            # Give Windows a moment to stabilize focus
            time.sleep(0.5)
            
            # Final validation: check if the active window is actually Warp
            active_hwnd = win32gui.GetForegroundWindow()
            active_title = win32gui.GetWindowText(active_hwnd).lower()
            
            # 1. Direct HWND comparison (most reliable)
            # 2. If HWND doesn't match, check if the title contains keywords
            keywords = ('warp', 'ready', 'working', 'mvp', 'terminal', 'cmd', 'powershell')
            is_valid = (active_hwnd == win._hWnd) or any(kw in active_title for kw in keywords)

            if not is_valid:
                logger.error(f"Safety Abort: Active window '{active_title}' (HWND: {active_hwnd}) is not Warp (Warp HWND: {win._hWnd}).")
                self.speak("Abortado por segurança. O terminal não parece estar em foco.")
                return

            # 4. Execute commands
            try:
                logger.info("Opening new tab and executing commands...")
                # Open new tab (Warp shortcut)
                pyautogui.hotkey('ctrl', 'shift', 't')
                time.sleep(1.2) # Wait for tab animation

                for cmd in self.commands:
                    logger.info(f"Typing: {cmd}")
                    self.type_text(cmd)
                    pyautogui.press("enter")
                    time.sleep(0.6)
                
                logger.info("Commands executed successfully.")
                self.speak("Pronto!")
            except Exception as e:
                logger.error(f"Error executing commands: {e}")
                self.speak("Erro ao executar os comandos.")
        else:
            logger.warning("Could not activate Warp window.")
            self.speak("Não consegui focar na janela do Warp.")
