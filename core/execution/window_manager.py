import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import psutil
import pyautogui
import pyperclip
import win32com.client
import win32con
import win32gui
import win32process

from core.infra.logger_config import logger
from core.shared.constants import Timing


@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    executable: str
    title: str


class WindowManager:
    def find_processes(
        self, executable_path: str | None = None, executable_name: str | None = None
    ) -> set[int]:
        pids = set()
        for p in psutil.process_iter(attrs=["pid", "name", "exe"]):
            try:
                if not executable_path and not executable_name:
                    pids.add(p.info["pid"])
                    continue
                if executable_path:
                    normalized_p_exe = os.path.normpath(p.info.get("exe") or "").lower()
                    normalized_target = os.path.normpath(executable_path).lower()
                    if normalized_p_exe == normalized_target:
                        pids.add(p.info["pid"])
                        continue
                if executable_name:
                    p_name = (p.info.get("name") or "").lower()
                    target_name = executable_name.lower()
                    if p_name == target_name:
                        pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return pids

    def get_foreground_window_info(self) -> WindowInfo | None:
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
        if not active_win:
            return False
        if active_win.hwnd == target_win.hwnd:
            return True
        if active_win.pid == target_win.pid:
            return True
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
        if not candidate_pids and not executable_name and not window_title_pattern:
            return None

        def enum_window_callback(
            hwnd: int, matching_windows_list: list[WindowInfo]
        ) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
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
                logger.debug(f"Error in enum_window_callback: {ex}")
            return True

        start_time = time.time()
        while time.time() - start_time < timeout:
            matching_windows: list[WindowInfo] = []
            try:
                win32gui.EnumWindows(enum_window_callback, matching_windows)
            # wait_for_window loop retry
            except Exception as e:
                logger.error(f"Error enumerating windows: {e}")
            if matching_windows:
                return matching_windows[0]
            time.sleep(Timing.WINDOW_SEARCH_SLEEP)
        return None

    def activate_window_by_hwnd(self, hwnd: int) -> bool:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            time.sleep(Timing.POST_FOCUS_RENDER_SLEEP)
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys("%")
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.warning(f"Focus error: {e}")
            time.sleep(Timing.WINDOW_RECOVERY_SLEEP)
            return True
        except Exception as e:
            logger.error(f"Error activating window: {e}")
            return False

    def open_and_stabilize_app(
        self,
        target: str,
        window_title_pattern: str | None = None,
        process_name: str | None = None,
        timeouts: dict[str, Any] | None = None,
    ) -> WindowInfo:
        t_out = timeouts or {}
        proc_start_timeout = t_out.get("process_start", 5.0)
        win_timeout = t_out.get("window_appear", 10.0)
        focus_timeout = t_out.get("focus", 3.0)
        focus_retries = t_out.get("focus_retries", 3)

        is_url = target.startswith(("http://", "https://"))
        pids_before = self.find_processes()

        if (
            not is_url
            and os.path.exists(target)
            and target.endswith((".exe", ".bat", ".cmd"))
        ):
            subprocess.Popen(target)
        else:
            os.startfile(target)

        candidate_pids = set()
        start_proc = time.time()
        while time.time() - start_proc < proc_start_timeout:
            current_pids = self.find_processes()
            candidate_pids = current_pids - pids_before
            if candidate_pids:
                break
            time.sleep(Timing.UI_STABILIZATION_SHORT)

        if not process_name and not is_url and target.lower().endswith(".exe"):
            process_name = os.path.basename(target)

        window = self.wait_for_window(
            candidate_pids=candidate_pids,
            executable_name=process_name,
            window_title_pattern=window_title_pattern,
            timeout=win_timeout,
        )

        if not window:
            raise TimeoutError(f"Window for '{target}' not found.")

        for _ in range(focus_retries):
            self.activate_window_by_hwnd(window.hwnd)
            start_focus = time.time()
            while time.time() - start_focus < focus_timeout:
                active_win = self.get_foreground_window_info()
                if active_win:
                    if self.check_focus_match(active_win, window, window_title_pattern):
                        try:
                            rect = win32gui.GetWindowRect(window.hwnd)
                            cx = rect[0] + (rect[2] - rect[0]) // 2
                            cy = rect[1] + (rect[3] - rect[1]) // 2
                            pyautogui.click(cx, cy)
                            time.sleep(Timing.UI_STABILIZATION_MEDIUM)
                        except Exception:
                            pass
                        return window
                else:
                    return window
                time.sleep(Timing.UI_STABILIZATION_SHORT)

        raise TimeoutError(f"Could not confirm focus on window for '{target}'.")

    def type_text(self, text: str) -> None:
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(Timing.WINDOW_SEARCH_SLEEP)
        # end of type_text method
        except Exception as e:
            logger.error(f"Error typing text: {e}")
