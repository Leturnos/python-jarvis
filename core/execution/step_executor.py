import shlex
import subprocess
import time
from typing import Any

import pyautogui

from core.audio.tts_engine import TTSEngine
from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.window_manager import WindowInfo, WindowManager
from core.infra.logger_config import logger
from core.media.spotify_automator import SpotifyAutomator
from core.shared.constants import AppRegistry


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
                if self._current_plan_window:
                    active_win = self.window_manager.get_foreground_window_info()
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
                                f"Safety Abort: Foreground focus lost. Expected: {self._current_plan_window.title} (HWND: {self._current_plan_window.hwnd}). Active: {active_win.title}."
                            )
                            self.tts_engine.speak(
                                "Abortado por segurança. O aplicativo alvo perdeu o foco."
                            )
                            return False

            if step.type == StepType.COMMAND:
                cmd = str(step.payload.get("command", "")).strip()
                if not cmd:
                    logger.error("Command execution failed: command payload is empty.")
                    return False

                first_arg = cmd.split()[0].lower() if cmd.split() else ""

                # CMD shell builtins list (excluding 'start' for safety)
                builtins = {
                    "dir",
                    "echo",
                    "cls",
                    "set",
                    "copy",
                    "del",
                    "cd",
                    "md",
                    "rd",
                    "ren",
                }

                try:
                    if first_arg in builtins:
                        # Validate against command injection metacharacters
                        dangerous_chars = {"&", "|", ";", "<", ">", "%", "^", "(", ")"}
                        if any(c in cmd for c in dangerous_chars):
                            logger.error(
                                f"Security Block: Shell builtin command contains dangerous characters: {cmd}"
                            )
                            self.tts_engine.speak(
                                "Comando bloqueado por conter caracteres especiais perigosos."
                            )
                            return False

                        subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
                    else:
                        cmd_args = shlex.split(cmd, posix=False)
                        # Strip outer quotes from parsed arguments to match expected subprocess behavior
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

                if not process_name and AppRegistry.SPOTIFY_APP_NAME in target.lower():
                    process_name = AppRegistry.SPOTIFY_PROCESS
                    if not window_title_pattern:
                        window_title_pattern = AppRegistry.SPOTIFY_APP_NAME

                window = self.window_manager.open_and_stabilize_app(
                    target=target,
                    window_title_pattern=window_title_pattern,
                    process_name=process_name,
                    timeouts=self.config.get("timeouts"),
                )
                self._current_plan_window = window
                self._current_plan_window_pattern = window_title_pattern
                return True
            elif step.type == StepType.WRITE:
                text_val = step.payload.get("text")
                text_str = str(text_val) if text_val is not None else ""
                self.window_manager.type_text(text_str)
                return True
            elif step.type == StepType.NAVIGATE:
                target = str(step.payload.get("target", ""))
                # Safely navigate by typing the directory change in the active terminal window
                self.window_manager.type_text(f"cd /d {target}")
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
