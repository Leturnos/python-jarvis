import re
import shlex
import subprocess
import time
from typing import Any

import pyautogui

try:
    import win32gui
except ImportError:
    win32gui = None

try:
    from plyer import notification
except ImportError:
    notification = None

from core.audio.tts_engine import TTSEngine
from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.window_manager import WindowInfo, WindowLayoutManager, WindowManager
from core.infra.logger_config import logger
from core.media.spotify_automator import SpotifyAutomator
from core.shared.constants import AppRegistry


def find_window_handle(title_or_process: str) -> int:
    """Finds window handle by title or process name using Win32 API."""
    if not win32gui:
        return 0
    try:
        hwnd = win32gui.FindWindow(None, title_or_process)
        if hwnd:
            return int(hwnd)

        matches: list[int] = []

        def enum_cb(h: int, res: list[int]) -> bool:
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if title_or_process.lower() in t.lower():
                    res.append(h)
            return True

        win32gui.EnumWindows(enum_cb, matches)
        return int(matches[0]) if matches else 0
    except Exception:
        return 0


def poll_window_handle(
    title_or_process: str, timeout: float = 5.0, interval: float = 0.2
) -> int:
    """Polls for active window handle creation up to timeout seconds."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        hwnd = find_window_handle(title_or_process)
        if hwnd > 0:
            return hwnd
        time.sleep(interval)
    return 0


def notify_partial_failure(app_name: str, reason: str) -> None:
    """Displays a Windows toast notification on partial execution failure."""
    if not notification:
        return
    try:
        notification.notify(
            title="Jarvis - Warning",
            message=f"Could not prepare '{app_name}': {reason}",
            app_name="Jarvis",
            timeout=4,
        )
    except Exception as e:
        logger.warning(f"Failed to send toast notification: {e}")


class StepExecutor:
    def __init__(
        self,
        config: dict[str, Any],
        window_manager: WindowManager,
        spotify_automator: SpotifyAutomator,
        tts_engine: TTSEngine,
    ) -> None:
        self.config = config
        self.window_manager = window_manager
        self.spotify_automator = spotify_automator
        self.tts_engine = tts_engine
        self._current_plan_window: WindowInfo | None = None
        self._current_plan_window_pattern: str | None = None

    def clear_session_state(self) -> None:
        self._current_plan_window = None
        self._current_plan_window_pattern = None

    def execute_step(self, step: ExecutionStep) -> bool:
        try:
            if step.type in (
                StepType.WRITE,
                StepType.TYPE_AND_ENTER,
                StepType.HOTKEY,
                StepType.NAVIGATE,
            ):
                active_win = self.window_manager.get_foreground_window_info()
                if self._current_plan_window is None and active_win is not None:
                    # Bind to the active window on first typing step if no OPEN_APP step set it
                    self._current_plan_window = active_win

                if self._current_plan_window:
                    if not self.window_manager.check_focus_match(
                        active_win,
                        self._current_plan_window,
                        self._current_plan_window_pattern,
                    ):
                        if active_win is None:
                            logger.warning(
                                "Active window is None during typing step. Allowing execution as fallback."
                            )
                        else:
                            logger.error(
                                f"Focus mismatch: active window '{active_win.title}' does not match expected window '{self._current_plan_window.title}'"
                            )
                            return False

            if step.type == StepType.COMMAND:
                cmd = str(step.payload.get("command", ""))
                try:
                    is_cmd = self.config.get("integrations", {}).get("use_cmd", False)
                    if is_cmd:
                        dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">"]
                        if any(char in cmd for char in dangerous_chars):
                            logger.error(
                                "Comando bloqueado por conter caracteres especiais perigosos."
                            )
                            return False

                        subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
                    else:
                        cmd_args = shlex.split(cmd, posix=False)
                        cmd_args = [
                            arg[1:-1]
                            if (
                                len(arg) >= 2
                                and arg[0] == arg[-1]
                                and arg[0] in ('"', "'")
                            )
                            else arg
                            for arg in cmd_args
                        ]
                        if cmd_args:
                            subprocess.run(cmd_args, shell=False, check=True)
                        else:
                            logger.error(
                                f"Command execution failed: shlex parsed empty args from {cmd}"
                            )
                            return False
                    return True
                except FileNotFoundError as e:
                    logger.error(f"Command executable not found: {e}")
                    self.tts_engine.speak(
                        "O sistema não conseguiu encontrar o executável especificado."
                    )
                    return False
                except subprocess.CalledProcessError as e:
                    logger.error(f"Command failed with exit code {e.returncode}: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Error executing command: {e}")
                    return False
            elif step.type == StepType.OPEN_APP:
                target = str(step.payload.get("target", ""))
                window_title_pattern = step.payload.get("window_title_pattern")
                process_name = step.payload.get("process_name")
                window_state = step.payload.get("window_state")

                if not process_name and AppRegistry.SPOTIFY_APP_NAME in target.lower():
                    process_name = AppRegistry.SPOTIFY_PROCESS
                    if not window_title_pattern:
                        window_title_pattern = AppRegistry.SPOTIFY_APP_NAME

                try:
                    window = self.window_manager.open_and_stabilize_app(
                        target=target,
                        window_title_pattern=window_title_pattern,
                        process_name=process_name,
                        timeouts=self.config.get("timeouts"),
                    )
                    self._current_plan_window = window
                    self._current_plan_window_pattern = window_title_pattern

                    if window_state and window:
                        layout_mgr = WindowLayoutManager()
                        layout_mgr.apply_window_state(window.hwnd, window_state)

                    return True
                except Exception as e:
                    logger.warning(f"App launch partial failure for '{target}': {e}")
                    notify_partial_failure(target, str(e))
                    return True
            elif step.type == StepType.WRITE:
                text_val = step.payload.get("text")
                text_str = str(text_val) if text_val is not None else ""
                self.window_manager.type_text(text_str)
                return True
            elif step.type == StepType.NAVIGATE:
                target = str(step.payload.get("target", ""))
                clean_target = re.sub(r"[\r\n;&|]", "", target).strip()
                self.window_manager.type_text(f"cd /d {clean_target}")
                pyautogui.press("enter")
                return True
            elif step.type == StepType.WAIT:
                duration = step.payload.get("duration", 1.0)
                time.sleep(float(duration))
                return True
            elif step.type == StepType.HOTKEY:
                keys = step.payload.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                return True
            elif step.type == StepType.TYPE_AND_ENTER:
                text_val = step.payload.get("text")
                text_str = str(text_val) if text_val is not None else ""
                self.window_manager.type_text(text_str)
                pyautogui.press("enter")
                return True
            elif step.type == StepType.FOCUS_WINDOW:
                target = step.payload.get("target", "")
                if target == AppRegistry.SPOTIFY_APP_NAME:
                    return bool(self.spotify_automator.activate_spotify_window())
                return True
            elif step.type == StepType.SPOTIFY_CLICK_PLAY:
                click_type = step.payload.get("click_type", "search")
                uri = step.payload.get("uri")
                return bool(
                    self.spotify_automator.spotify_click_play(
                        click_type=click_type, uri=uri
                    )
                )
            return False
        except Exception as e:
            logger.error(f"Step execution error ({step.type.value}): {e}")
            return False
