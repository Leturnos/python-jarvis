import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import psutil
import pyautogui
import pygetwindow as gw
import pyperclip
import pythoncom  # Required for COM in multiple threads on Windows
import win32com.client
import win32con
import win32gui
import win32process

from core.infra.logger_config import logger
from core.shared.utils import time_it


@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    executable: str
    title: str


class WarpAutomator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.warp_path = ""
        self.commands: list[str] = []
        self.last_spoken_text = ""
        self.last_spoken_time = 0.0
        self.is_speaking = False

        # Dedicated TTS Thread to avoid blocking and thread-safety issues
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self._stop_tts = threading.Event()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def _tts_worker(self) -> None:
        """Dedicated worker for TTS processing using native Windows SAPI5."""
        try:
            # Initialize COM in this thread
            pythoncom.CoInitialize()

            # Use Dispatch directly for better stability
            voice = win32com.client.Dispatch("SAPI.SpVoice")

            # Find a Portuguese voice if available
            voice_keyword = (
                self.config.get("tts", {}).get("voice_keyword", "maria").lower()
            )
            try:
                available_voices = voice.GetVoices()
                logger.debug(f"Available SAPI Voices ({available_voices.Count}):")
                selected_voice = None

                for i in range(available_voices.Count):
                    v = available_voices.Item(i)
                    desc = v.GetDescription()
                    logger.debug(f" - [{i}] {desc}")
                    if voice_keyword in desc.lower():
                        selected_voice = v

                if selected_voice:
                    voice.Voice = selected_voice
                    logger.info(
                        f"SAPI Voice selected: {selected_voice.GetDescription()}"
                    )
                else:
                    # Fallback: search for any Portuguese voice if Maria is not found
                    for i in range(available_voices.Count):
                        v = available_voices.Item(i)
                        desc = v.GetDescription().lower()
                        if "portuguese" in desc or "brazil" in desc:
                            voice.Voice = v
                            logger.info(
                                f"Fallback SAPI Voice selected (Portuguese): {v.GetDescription()}"
                            )
                            break
                    else:
                        logger.warning(
                            f"Voice keyword '{voice_keyword}' not found and no Portuguese fallback available."
                        )
            except Exception as e:
                logger.debug(f"Default voice will be used: {e}")

            # SAPI Rate is -10 to 10 (0 is normal)
            voice.Rate = 2
            voice.Volume = 100

            while not self._stop_tts.is_set():
                try:
                    # Non-blocking check for items in queue
                    text = self._speech_queue.get(timeout=0.5)
                    self.is_speaking = True
                    logger.info(f"Jarvis is speaking: '{text}'")

                    # 0 = Synchronous speak (fine because we are in a dedicated worker thread)
                    voice.Speak(text, 0)

                    self.is_speaking = False
                    self.last_spoken_time = time.time()
                    self._speech_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    self.is_speaking = False
                    logger.error(f"SAPI TTS error: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize SAPI5: {e}")
        finally:
            pythoncom.CoUninitialize()
            logger.info("TTS Worker thread finishing.")

    def speak(self, text: str) -> None:
        """Adds text to the speech queue with deduplication."""
        now = time.time()
        if text == self.last_spoken_text and (now - self.last_spoken_time) < 2.0:
            logger.debug(f"Skipping duplicate speech: {text}")
            return

        self.last_spoken_text = text
        self._speech_queue.put(text)

    def find_processes(
        self, executable_path: str | None = None, executable_name: str | None = None
    ) -> set[int]:
        """Find running processes matching the given executable name or path."""
        pids = set()
        for p in psutil.process_iter(attrs=["pid", "name", "exe"]):
            try:
                if not executable_path and not executable_name:
                    pids.add(p.info["pid"])
                    continue
                # Check path
                if executable_path:
                    normalized_p_exe = os.path.normpath(p.info.get("exe") or "").lower()
                    normalized_target = os.path.normpath(executable_path).lower()
                    if normalized_p_exe == normalized_target:
                        pids.add(p.info["pid"])
                        continue
                # Check name
                if executable_name:
                    p_name = (p.info.get("name") or "").lower()
                    target_name = executable_name.lower()
                    if p_name == target_name:
                        pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return pids

    def get_foreground_window_info(self) -> WindowInfo | None:
        """Gets info about the current foreground window."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            title = win32gui.GetWindowText(hwnd)
            executable = ""
            try:
                p = psutil.Process(pid)
                executable = p.name()
            except Exception:
                pass
            return WindowInfo(hwnd=hwnd, pid=pid, executable=executable, title=title)
        except Exception as e:
            logger.error(f"Error getting foreground window info: {e}")
            return None

    def check_focus_match(
        self,
        active_win: WindowInfo | None,
        target_win: WindowInfo,
        window_title_pattern: str | None = None,
    ) -> bool:
        """Verifies if the active window matches the target window based on strict safety rules."""
        if not active_win:
            return False

        # Rule 1: Direct HWND comparison
        if active_win.hwnd == target_win.hwnd:
            return True

        # Rule 2: PID comparison
        if active_win.pid == target_win.pid:
            return True

        # Rule 3: Executable comparison AND title matches regex
        if (
            active_win.executable.lower() == target_win.executable.lower()
            and window_title_pattern
            and re.search(window_title_pattern, active_win.title, re.IGNORECASE)
        ):
            return True

        return False

    def wait_for_window(
        self,
        candidate_pids: set[int] | None = None,
        executable_name: str | None = None,
        window_title_pattern: str | None = None,
        timeout: float = 10.0,
    ) -> WindowInfo | None:
        """Waits for a visible window matching candidate PIDs, executable name, or title pattern."""
        if not candidate_pids and not executable_name and not window_title_pattern:
            logger.warning(
                "wait_for_window called with no search criteria. Aborting search."
            )
            return None

        def enum_window_callback(
            hwnd: int, matching_windows_list: list[WindowInfo]
        ) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:  # Filter out invisible or empty title helper windows
                        try:
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        except Exception:
                            return True

                        executable = ""
                        try:
                            p = psutil.Process(pid)
                            executable = p.name()
                        except Exception:
                            pass

                        info = WindowInfo(
                            hwnd=hwnd, pid=pid, executable=executable, title=title
                        )

                        # Check match criteria
                        is_match = False
                        if candidate_pids and pid in candidate_pids:
                            is_match = True
                        elif (
                            executable_name
                            and executable.lower() == executable_name.lower()
                        ):
                            is_match = True
                        elif window_title_pattern and re.search(
                            window_title_pattern, title, re.IGNORECASE
                        ):
                            is_match = True

                        if is_match:
                            matching_windows_list.append(info)
            except Exception as ex:
                logger.debug(f"Error in enum_window_callback for hwnd {hwnd}: {ex}")
            return True

        start_time = time.time()
        while time.time() - start_time < timeout:
            matching_windows: list[WindowInfo] = []

            try:
                win32gui.EnumWindows(enum_window_callback, matching_windows)
            except Exception as e:
                logger.error(f"Error enumerating windows: {e}")

            if matching_windows:
                # Return the first matching window (usually the main one)
                logger.info(f"Window found: {matching_windows[0]}")
                return matching_windows[0]

            time.sleep(0.2)

        logger.warning("wait_for_window timed out without finding a match.")
        return None

    def activate_window_by_hwnd(self, hwnd: int) -> bool:
        """Brings a window to the foreground using its HWND."""
        try:
            logger.info(f"Activating window HWND: {hwnd}")
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            time.sleep(0.5)

            try:
                # ALT key trick to steal focus on Windows
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys("%")
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.warning(f"Focus error on SetForegroundWindow: {e}")

            time.sleep(0.4)
            return True
        except Exception as e:
            logger.error(f"Error activating window by HWND: {e}")
            return False

    def open_and_stabilize_app(
        self,
        target: str,
        window_title_pattern: str | None = None,
        process_name: str | None = None,
    ) -> WindowInfo:
        """Launches an application or URL, tracks its process/window, and securely focuses it."""
        timeouts = self.config.get("timeouts", {})
        proc_start_timeout = timeouts.get("process_start", 5.0)
        win_timeout = timeouts.get("window_appear", 10.0)
        focus_timeout = timeouts.get("focus", 3.0)
        focus_retries = timeouts.get("focus_retries", 3)

        is_url = target.startswith(("http://", "https://"))
        pids_before = self.find_processes()

        # 1. Launch
        logger.info(f"Opening target: {target}")
        if (
            not is_url
            and os.path.exists(target)
            and target.endswith((".exe", ".bat", ".cmd"))
        ):
            subprocess.Popen(target)
        else:
            os.startfile(target)

        # 2. Track candidate PIDs dynamically (no static sleep)
        candidate_pids = set()
        start_proc = time.time()
        while time.time() - start_proc < proc_start_timeout:
            current_pids = self.find_processes()
            candidate_pids = current_pids - pids_before
            if candidate_pids:
                break
            time.sleep(0.1)

        # Handle UWP/Indirect/Launcher processes or standard executables
        if not process_name and not is_url and target.lower().endswith(".exe"):
            process_name = os.path.basename(target)

        # Detect Spotify protocol targets to prevent window discovery timeouts
        if not process_name and "spotify" in target.lower():
            process_name = "spotify.exe"
            if not window_title_pattern:
                window_title_pattern = "spotify"

        logger.info(f"Candidate PIDs: {candidate_pids}, process_name: {process_name}")

        # 3. Wait for the visible window
        window = self.wait_for_window(
            candidate_pids=candidate_pids,
            executable_name=process_name,
            window_title_pattern=window_title_pattern,
            timeout=win_timeout,
        )

        if not window:
            raise TimeoutError(
                f"Window for '{target}' not found within window_appear timeout."
            )

        # 4. Focus loop with strict validation
        for attempt in range(focus_retries):
            logger.info(
                f"Focus attempt {attempt + 1}/{focus_retries} for HWND {window.hwnd}"
            )
            self.activate_window_by_hwnd(window.hwnd)

            # Polling to check if window is focused
            start_focus = time.time()
            while time.time() - start_focus < focus_timeout:
                active_win = self.get_foreground_window_info()
                if active_win:
                    if self.check_focus_match(active_win, window, window_title_pattern):
                        try:
                            rect = win32gui.GetWindowRect(window.hwnd)
                            width = rect[2] - rect[0]
                            height = rect[3] - rect[1]
                            center_x = rect[0] + width // 2
                            center_y = rect[1] + height // 2
                            logger.info(
                                f"Clicking at ({center_x}, {center_y}) to establish input focus"
                            )
                            pyautogui.click(center_x, center_y)
                            time.sleep(0.3)
                        except Exception as click_err:
                            logger.warning(
                                f"Could not click window center: {click_err}"
                            )

                        logger.info("Window focus successfully validated!")
                        return window
                else:
                    logger.warning(
                        "Active window is None (no foreground window). This might be a non-interactive session. Proceeding."
                    )
                    return window
                time.sleep(0.1)

        raise TimeoutError(
            f"Could not confirm foreground focus on window for '{target}'."
        )

    def is_open(self) -> bool:
        """Checks if the Warp process is running."""
        try:
            for p in psutil.process_iter(["name"]):
                if p.info["name"] and "warp" in p.info["name"].lower():
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        return False

    def find_window(self) -> Any:
        """Finds the Warp terminal window using PID or title matching."""
        try:
            # 1. Get all PIDs for processes named "warp"
            warp_pids = set()
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] and "warp" in p.info["name"].lower():
                    warp_pids.add(p.info["pid"])

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
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error searching for Warp window: {e}")

        # Fallback to title search
        keywords = ("warp", "ready", "working", "mvp")
        for w in gw.getAllWindows():
            if w.title and any(kw in w.title.lower() for kw in keywords):
                return w

        return None

    def activate_window(self, win: Any) -> bool:
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
                shell.SendKeys("%")
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

    def type_text(self, text: str) -> None:
        """Types text using the clipboard to handle special characters."""
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error typing text: {e}")

    @time_it
    def run_workflow(self) -> None:
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
        for _ in range(20):  # Up to 10 seconds total
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
            keywords = (
                "warp",
                "ready",
                "working",
                "mvp",
                "terminal",
                "cmd",
                "powershell",
            )
            is_valid = (active_hwnd == win._hWnd) or any(
                kw in active_title for kw in keywords
            )

            if not is_valid:
                logger.error(
                    f"Safety Abort: Active window '{active_title}' (HWND: {active_hwnd}) is not Warp (Warp HWND: {win._hWnd})."
                )
                self.speak(
                    "Abortado por segurança. O terminal não parece estar em foco."
                )
                return

            # 4. Execute commands
            try:
                logger.info("Opening new tab and executing commands...")
                # Open new tab (Warp shortcut)
                pyautogui.hotkey("ctrl", "shift", "t")
                time.sleep(1.2)  # Wait for tab animation

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

    def find_spotify_window(self) -> Any:
        """Finds the Spotify window using process name search."""
        try:
            spotify_pids = set()
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] and "spotify" in p.info["name"].lower():
                    spotify_pids.add(p.info["pid"])

            if not spotify_pids:
                logger.debug("No Spotify processes found.")
                return None

            for w in gw.getAllWindows():
                if w._hWnd:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(w._hWnd)
                        if pid in spotify_pids and w.title:
                            return w
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error searching for Spotify window: {e}")
        return None

    def activate_spotify_window(self) -> bool:
        """Brings the Spotify window to the foreground without clicking."""
        win = self.find_spotify_window()
        if not win:
            logger.warning("Spotify window not found.")
            return False
        try:
            hwnd = win._hWnd
            logger.info(f"Activating Spotify window HWND: {hwnd}")
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            time.sleep(0.5)

            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.warning(f"SetForegroundWindow failed: {e}")
                try:
                    win.activate()
                except Exception as ex:
                    logger.warning(f"Focus error on Spotify window: {ex}")

            time.sleep(0.4)
            return True
        except Exception as e:
            logger.error(f"Error activating Spotify window: {e}")
            return False

    def is_spotify_playing(self) -> bool:
        """Checks if Spotify is currently playing a song based on the window title."""
        win = self.find_spotify_window()
        if not win or not win.title:
            return False
        title = win.title.lower().strip()
        non_playing = {"spotify", "spotify premium", "spotify free"}
        return title not in non_playing

    def find_spotify_green_button(
        self, haystack: Any, scale_factor: float = 1.0
    ) -> Any:
        """
        Locates the Spotify green play button by searching for its distinct green color (#1DB954).
        Returns a namedtuple Box-like object compatible with the return type of locate_template_multiscale,
        or None if not found.
        """
        from collections import namedtuple

        try:
            # Convert to HSV for better color segmentation
            hsv = cv2.cvtColor(haystack, cv2.COLOR_BGR2HSV)

            # Spotify green in HSV is roughly H=141 (70 in OpenCV), S=84%, V=72%
            # OpenCV HSV ranges: H: 0-180, S: 0-255, V: 0-255
            # We use a broad threshold for safety to capture the green button variations
            lower_green = np.array([55, 100, 100])
            upper_green = np.array([85, 255, 255])

            mask = cv2.inRange(hsv, lower_green, upper_green)

            # Find contours of the green blobs
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            best_center = None
            best_area = 0.0
            best_rect = None

            for cnt in contours:
                area = cv2.contourArea(cnt)
                # The play button should be a reasonable size in pixels (accounting for DPI scaling)
                min_area = 80 * (scale_factor**2)
                max_area = 8000 * (scale_factor**2)
                if min_area <= area <= max_area:
                    # Get the bounding box to check aspect ratio (should be roughly square/circle)
                    x, y, w, h = cv2.boundingRect(cnt)
                    aspect_ratio = float(w) / h
                    if 0.75 <= aspect_ratio <= 1.25:
                        if area > best_area:
                            best_area = area
                            best_rect = (x, y, w, h)
                            m = cv2.moments(cnt)
                            if m["m00"] != 0:
                                cx = int(m["m10"] / m["m00"])
                                cy = int(m["m01"] / m["m00"])
                                best_center = (cx, cy)

            if best_center and best_rect:
                x, y, w, h = best_rect
                logger.info(
                    f"Located Spotify green play button using color masking at relative ({best_center[0]}, {best_center[1]}), area={best_area}"
                )
                Box = namedtuple("Box", ["left", "top", "width", "height"])
                return Box(x, y, w, h)
        except Exception as e:
            logger.error(f"Error in find_spotify_green_button: {e}")

        return None

    def locate_template_multiscale(
        self,
        template_path: str,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.7,
    ) -> Any:
        """
        Locates a template image on the screen using multi-scale OpenCV matching.
        Attempts scale 1.0 first for speed, then falls back to restricted scales to tolerate zoom/DPI differences.
        """
        import os

        try:
            # 1. Take screenshot of the region
            screenshot = pyautogui.screenshot(region=region)
            haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)

            template = cv2.imread(template_path)
            if template is None:
                logger.error(f"Template not found at: {template_path}")
                return None
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            best_val = -1.0
            best_loc = None
            best_scale = None

            # A. Try direct match at scale 1.0 first
            w = template_gray.shape[1]
            h = template_gray.shape[0]
            if w <= haystack_gray.shape[1] and h <= haystack_gray.shape[0]:
                res = cv2.matchTemplate(
                    haystack_gray, template_gray, cv2.TM_CCOEFF_NORMED
                )
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= confidence:
                    best_val = max_val
                    best_loc = max_loc
                    best_scale = 1.0
                    logger.info(
                        f"Direct match (scale 1.0) for {os.path.basename(template_path)}: confidence {best_val:.4f} at {best_loc}"
                    )

            # B. Fallback to restricted multiscale if scale 1.0 fails or confidence is low
            if best_val < confidence:
                scales = [
                    0.9,
                    1.1,
                    1.25,
                    0.8,
                ]  # Restricted, safe range to prevent false positives and improve speed
                for scale in scales:
                    w = int(template_gray.shape[1] * scale)
                    h = int(template_gray.shape[0] * scale)
                    if (
                        w > haystack_gray.shape[1]
                        or h > haystack_gray.shape[0]
                        or w < 10
                        or h < 10
                    ):
                        continue

                    resized = cv2.resize(template_gray, (w, h))
                    res = cv2.matchTemplate(
                        haystack_gray, resized, cv2.TM_CCOEFF_NORMED
                    )
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    if max_val > best_val:
                        best_val = max_val
                        best_loc = max_loc
                        best_scale = scale

                logger.info(
                    f"Multiscale match for {os.path.basename(template_path)}: best confidence {best_val:.4f} at scale {best_scale} at {best_loc}"
                )

            if best_val >= confidence and best_loc is not None:
                w = int(template_gray.shape[1] * best_scale)
                h = int(template_gray.shape[0] * best_scale)

                # The coordinates returned by matchTemplate are relative to the screenshot region
                left_rel, top_rel = best_loc
                region_left = region[0] if region else 0
                region_top = region[1] if region else 0

                screen_x = region_left + left_rel
                screen_y = region_top + top_rel

                from collections import namedtuple

                Box = namedtuple("Box", ["left", "top", "width", "height"])
                return Box(screen_x, screen_y, w, h)
        except Exception as e:
            logger.error(f"Error in multiscale template matching: {e}")

        return None

    def spotify_click_play(
        self, click_type: str = "search", uri: str | None = None
    ) -> bool:
        """
        Main autoplay logic:
        - For 'playlist': tries to locate the green play button (spotify_play_button.png) on the screen.
          If found (using confidence=0.7 for gradients), clicks it directly. If not, falls back to clicking
          exactly 10% higher than the center of the window to focus, followed by Tab + Enter.
        - For 'search': clicks on the top results card (using spotify_search_anchor.png template,
          config-defined absolute coordinates, or relative center fallback). It then waits 1.8s, checks if
          music is already playing, and if not, triggers the 'playlist' autoplay logic.
        """
        win = self.find_spotify_window()
        if not win:
            logger.warning("Spotify window not found.")
            return False
        try:
            # 1. Restore only if minimized, preserving maximized/normal state
            try:
                if win.isMinimized:
                    win.restore()
                    time.sleep(0.4)
            except Exception as ex:
                logger.warning(f"Failed to restore Spotify window: {ex}")

            if not self.activate_spotify_window():
                return False

            # Wait for window render/animation
            time.sleep(0.5)

            # 2. Get precise per-monitor DPI scale factor via ctypes
            import ctypes

            try:
                # Set per-monitor DPI awareness
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # 88 = LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)
                scale_factor = dpi / 96.0
            except Exception as ex:
                logger.warning(
                    f"Failed to calculate DPI scale factor, defaulting to 1.0: {ex}"
                )
                scale_factor = 1.0

            logger.info(
                f"Spotify window coordinates: left={win.left}, top={win.top}, width={win.width}, height={win.height}. DPI scale factor={scale_factor}"
            )

            from core.shared.utils import get_resources_dir

            click_x, click_y = None, None
            direct_play_clicked = False

            if click_type == "playlist":
                # Try to locate the big green play button on the playlist page
                play_button_matched = False

                try:
                    # Constrain region coordinates to screen bounds to avoid negative coordinate failures
                    try:
                        screen_w, screen_h = pyautogui.size()
                    except Exception:
                        screen_w, screen_h = 1920, 1080
                    left = max(0, win.left)
                    top = max(0, win.top)
                    width = min(screen_w - left, win.width)
                    height = min(screen_h - top, win.height)

                    # Convert to physical coordinates for pyautogui.screenshot region
                    region = (
                        int(left * scale_factor),
                        int(top * scale_factor),
                        int(width * scale_factor),
                        int(height * scale_factor),
                    )

                    # Take a screenshot of the region
                    screenshot = pyautogui.screenshot(region=region)

                    # Check if running in a test environment with mocked pyautogui
                    is_mock = hasattr(screenshot, "_spec_class") or type(
                        screenshot
                    ).__name__ in ("MagicMock", "Mock")

                    haystack = None
                    if not is_mock:
                        haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

                    # A. Attempt high-reliability color masking fallback first
                    pos = None
                    if haystack is not None:
                        pos = self.find_spotify_green_button(
                            haystack, scale_factor=scale_factor
                        )

                    if pos:
                        # Convert coordinates back to logical pixels (or keep physical if process is DPI-aware)
                        left_pos = getattr(pos, "left", pos[0])
                        top_pos = getattr(pos, "top", pos[1])
                        w_pos = getattr(pos, "width", pos[2])
                        h_pos = getattr(pos, "height", pos[3])

                        # Add relative offset to window origin
                        click_x_phys = int(
                            (left * scale_factor) + left_pos + w_pos // 2
                        )
                        click_y_phys = int((top * scale_factor) + top_pos + h_pos // 2)

                        click_x = click_x_phys
                        click_y = click_y_phys
                        play_button_matched = True
                        direct_play_clicked = True
                        logger.info(
                            f"Play button matched by color masking at physical ({click_x}, {click_y})"
                        )

                    # B. Fallback to multiscale template matching if color match fails
                    if not play_button_matched:
                        play_button_path = str(
                            get_resources_dir() / "spotify_play_button.png"
                        )
                        logger.info(
                            f"Searching for Spotify play button template: {play_button_path}"
                        )
                        pos = self.locate_template_multiscale(
                            play_button_path, region=region, confidence=0.7
                        )
                        if pos:
                            left_pos = getattr(pos, "left", pos[0])
                            top_pos = getattr(pos, "top", pos[1])
                            w_pos = getattr(pos, "width", pos[2])
                            h_pos = getattr(pos, "height", pos[3])
                            click_x = int(left_pos + w_pos // 2)
                            click_y = int(top_pos + h_pos // 2)
                            direct_play_clicked = True
                            logger.info(
                                f"Play button matched by template at physical ({click_x}, {click_y})"
                            )
                except Exception as ex:
                    logger.warning(
                        f"Failed image search matching for Spotify play button: {ex}"
                    )

                if not direct_play_clicked:
                    # Fallback click coordinate (10% higher than center)
                    click_x = win.left + win.width // 2
                    click_y = win.top + int(win.height * 0.4)
                    logger.info(
                        f"Play button not found. Clicking playlist area 10% higher at fallback relative ({click_x}, {click_y})"
                    )

                # Execute click for playlist
                logger.info(f"Clicking Spotify playlist area at ({click_x}, {click_y})")
                pyautogui.click(click_x, click_y)
                time.sleep(0.4)

                if not direct_play_clicked:
                    # Press Tab to focus the first play button / result item
                    logger.info("Sending Tab key to focus first result")
                    pyautogui.press("tab")
                    time.sleep(0.3)

                    # Press Enter to start playback
                    logger.info("Sending Enter key to play")
                    pyautogui.press("enter")
                    time.sleep(0.3)

                return True
            else:
                # "search"
                anchor_matched = False
                hover_x, hover_y = None, None

                # 1. Look for the "Melhor resultado" (PT) or "Top result" (EN) anchor image
                try:
                    anchor_pt_path = str(
                        get_resources_dir() / "spotify_search_anchor.png"
                    )
                    anchor_en_path = str(
                        get_resources_dir() / "spotify_search_anchor_en.png"
                    )

                    # Constrain region coordinates to screen bounds and ignore top bar to avoid false matches
                    try:
                        screen_w, screen_h = pyautogui.size()
                    except Exception:
                        screen_w, screen_h = 1920, 1080
                    left = max(0, win.left)
                    top = max(0, win.top + 120)  # Ignore top navigation bar
                    width = min(screen_w - left, win.width)
                    height = min(screen_h - top, win.height)

                    region = (
                        int(left * scale_factor),
                        int(top * scale_factor),
                        int(width * scale_factor),
                        int(height * scale_factor),
                    )

                    pos = None
                    # Try Portuguese template first
                    if os.path.exists(anchor_pt_path):
                        logger.info(f"Searching for PT search anchor: {anchor_pt_path}")
                        pos = self.locate_template_multiscale(
                            anchor_pt_path, region=region, confidence=0.4
                        )

                    # Try English template if PT fails
                    if not pos and os.path.exists(anchor_en_path):
                        logger.info(f"Searching for EN search anchor: {anchor_en_path}")
                        pos = self.locate_template_multiscale(
                            anchor_en_path, region=region, confidence=0.4
                        )

                    if pos:
                        left_pos = getattr(pos, "left", pos[0])
                        top_pos = getattr(pos, "top", pos[1])
                        w_pos = getattr(pos, "width", pos[2])
                        h_pos = getattr(pos, "height", pos[3])

                        # Set hover point to 10% of window height below the anchor center
                        hover_x_phys = int(left_pos + w_pos // 2)
                        hover_y_phys = int(
                            top_pos + h_pos // 2 + (win.height * scale_factor) * 0.1
                        )

                        hover_x = hover_x_phys
                        hover_y = hover_y_phys
                        anchor_matched = True
                        logger.info(
                            f"Anchor matched at physical ({left_pos}, {top_pos}). Calculated physical hover point: ({hover_x}, {hover_y})"
                        )
                except Exception as ex:
                    logger.warning(
                        f"Failed image search matching for Spotify search anchor: {ex}"
                    )

                # Fallback if anchor is not found
                if not anchor_matched:
                    media_config = self.config.get("media", {})
                    spotify_config = media_config.get("spotify", {})
                    search_x = spotify_config.get("search_click_x")
                    search_y = spotify_config.get("search_click_y")

                    if search_x is not None and search_y is not None:
                        hover_x = int(search_x)
                        hover_y = int(search_y)
                        logger.info(
                            f"Anchor not matched. Using absolute hover point ({hover_x}, {hover_y}) from config"
                        )
                    else:
                        # 25% width, 35% height fallback (Top Left region where search result card resides)
                        hover_x = win.left + int(win.width * 0.25)
                        hover_y = win.top + int(win.height * 0.35)
                        # Adjust for DPI scale since pyautogui click will be in physical pixels
                        hover_x = int(hover_x * scale_factor)
                        hover_y = int(hover_y * scale_factor)
                        logger.info(
                            f"Anchor not matched. Using robust relative 25%/35% hover point at physical ({hover_x}, {hover_y})"
                        )

                # 2. Move mouse to the hover position to reveal the play button
                logger.info(f"Moving mouse to hover position: ({hover_x}, {hover_y})")
                pyautogui.moveTo(hover_x, hover_y)
                time.sleep(0.5)

                # 3. Look for the green play button
                play_button_path = str(get_resources_dir() / "spotify_play_button.png")

                # Constrain region coordinates to screen bounds
                try:
                    screen_w, screen_h = pyautogui.size()
                except Exception:
                    screen_w, screen_h = 1920, 1080
                left = max(0, win.left)
                top = max(0, win.top)
                width = min(screen_w - left, win.width)
                height = min(screen_h - top, win.height)

                region = (
                    int(left * scale_factor),
                    int(top * scale_factor),
                    int(width * scale_factor),
                    int(height * scale_factor),
                )

                play_pos = None
                try:
                    # A. Try high-reliability color masking first
                    screenshot = pyautogui.screenshot(region=region)
                    is_mock = hasattr(screenshot, "_spec_class") or type(
                        screenshot
                    ).__name__ in ("MagicMock", "Mock")

                    haystack = None
                    if not is_mock:
                        haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

                    pos = None
                    if haystack is not None:
                        pos = self.find_spotify_green_button(
                            haystack, scale_factor=scale_factor
                        )

                    if pos:
                        left_pos = getattr(pos, "left", pos[0])
                        top_pos = getattr(pos, "top", pos[1])
                        w_pos = getattr(pos, "width", pos[2])
                        h_pos = getattr(pos, "height", pos[3])

                        click_x = int((left * scale_factor) + left_pos + w_pos // 2)
                        click_y = int((top * scale_factor) + top_pos + h_pos // 2)
                        play_pos = (click_x, click_y)
                        logger.info(
                            f"Play button matched after hover by color masking at physical ({click_x}, {click_y})"
                        )

                    # B. Fallback to template matching
                    if not play_pos:
                        logger.info(
                            f"Searching for Spotify play button template after hover: {play_button_path}"
                        )
                        t_pos = self.locate_template_multiscale(
                            play_button_path, region=region, confidence=0.7
                        )
                        if t_pos:
                            left_pos = getattr(t_pos, "left", t_pos[0])
                            top_pos = getattr(t_pos, "top", t_pos[1])
                            w_pos = getattr(t_pos, "width", t_pos[2])
                            h_pos = getattr(t_pos, "height", t_pos[3])
                            click_x = int(left_pos + w_pos // 2)
                            click_y = int(top_pos + h_pos // 2)
                            play_pos = (click_x, click_y)
                            logger.info(
                                f"Play button matched after hover by template at physical ({click_x}, {click_y})"
                            )
                except Exception as ex:
                    logger.warning(
                        f"Failed image search matching for Spotify play button: {ex}"
                    )

                if play_pos:
                    # Play button found! Click it directly
                    click_x, click_y = play_pos
                    pyautogui.click(click_x, click_y)

                    # Wait and check if playing
                    time.sleep(1.8)
                    if self.is_spotify_playing():
                        logger.info(
                            "Spotify is playing after clicking detected play button."
                        )
                        return True
                    logger.info(
                        "Spotify not playing after direct click. Falling back to hover click sequence."
                    )

                # Fallback: Click where the mouse was parked (opens result page), wait, and run playlist autoplay logic
                logger.info(
                    f"Clicking at parked mouse hover position ({hover_x}, {hover_y})"
                )
                pyautogui.click(hover_x, hover_y)
                time.sleep(1.8)

                logger.info("Calling playlist autoplay logic as fallback")
                return self.spotify_click_play(click_type="playlist", uri=uri)

            return True
        except Exception as e:
            logger.error(f"Error executing Spotify click and play ({click_type}): {e}")
            return False
