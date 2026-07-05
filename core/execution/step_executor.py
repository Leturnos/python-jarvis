import subprocess
import time
from typing import Any

import pyautogui

from core.audio.tts_engine import TTSEngine
from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.window_manager import WindowManager
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
        self._current_plan_window = None
        self._current_plan_window_pattern = None

    def clear_session_state(self) -> None:
        self._current_plan_window = None
        self._current_plan_window_pattern = None

    def execute_step(self, step: ExecutionStep) -> bool:
        try:
            if step.type in (StepType.WRITE, StepType.TYPE_AND_ENTER, StepType.HOTKEY):
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
                cmd = str(step.payload.get("command", ""))
                subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
                return True
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
                text = step.payload.get("text")
                self.window_manager.type_text(text)
                return True
            elif step.type == StepType.NAVIGATE:
                target = str(step.payload.get("target", ""))
                subprocess.run(
                    ["cmd", "/c", f"cd /d {target}"], shell=False, check=True
                )
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
                self.window_manager.type_text(step.payload.get("text", ""))
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
