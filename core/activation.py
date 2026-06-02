import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import keyboard
import win32api
import win32con
import win32gui

from core.runtime.state import JarvisState

logger = logging.getLogger(__name__)


class ActivationActionType(Enum):
    TRIGGER_WAKE = auto()
    TRIGGER_PTT_START = auto()
    TRIGGER_PTT_STOP = auto()
    SUSPEND = auto()
    RESUME = auto()
    NONE = auto()


@dataclass
class ActivationAction:
    action_type: ActivationActionType
    source: str  # WAKE_WORD, PTT, FULLSCREEN_APP, MANUAL, NONE


@dataclass
class ActivationContext:
    wakeword_score: float
    wakeword_detected: str | None
    is_fullscreen: bool
    is_hotkey_pressed: bool
    current_state: JarvisState
    timestamp: float


class ActivationManager:
    """Manages the logic for activating Jarvis via Wake Word or Push-To-Talk,
    and handles automatic suspension in contexts like fullscreen apps.
    """

    MIN_SUSPEND_DURATION = 2.0  # Hysteresis to prevent flickering

    def __init__(self, config: dict[str, Any]):
        self.full_config = config  # Keep reference for threshold lookup
        self.config = config.get("voice_activation", {})
        self.mode = self.config.get("mode", "hybrid")
        self.ptt_config = self.config.get("push_to_talk", {})
        self.ww_config = self.config.get("wake_word", {})
        self.auto_suspend = self.config.get("auto_suspend", {}).get("fullscreen", True)

        self.ptt_key = self.ptt_config.get("key", "ctrl+alt")
        self.ptt_behavior = self.ptt_config.get("behavior", "hold")

        # State tracking for hysteresis and transitions
        self.last_state_change_time = 0
        self.is_ptt_active = False

        # Metrics
        self.metrics = {
            "activation_wake_word": 0,
            "activation_ptt": 0,
            "activation_suspend": 0,
            "activation_resume": 0,
            "fullscreen_suspend_count": 0,
        }

    def evaluate(self, context: ActivationContext) -> ActivationAction:
        """Evaluates the current environment context and decides on an activation action."""

        # 1. Check for Fullscreen Suspension
        if self.auto_suspend and context.current_state == JarvisState.IDLE:
            if context.is_fullscreen:
                self._update_metric("activation_suspend")
                self._update_metric("fullscreen_suspend_count")
                self.last_state_change_time = context.timestamp
                return ActivationAction(ActivationActionType.SUSPEND, "FULLSCREEN_APP")

        if context.current_state == JarvisState.SUSPENDED:
            # Hysteresis: Don't resume too quickly
            if (
                not context.is_fullscreen
                and (context.timestamp - self.last_state_change_time)
                > self.MIN_SUSPEND_DURATION
            ):
                self._update_metric("activation_resume")
                self.last_state_change_time = context.timestamp
                return ActivationAction(ActivationActionType.RESUME, "FULLSCREEN_APP")
            return ActivationAction(ActivationActionType.NONE, "NONE")

        # 2. Check Push-To-Talk (Priority)
        if self.mode in ("hybrid", "push_to_talk"):
            if context.is_hotkey_pressed:
                if not self.is_ptt_active:
                    self.is_ptt_active = True
                    self._update_metric("activation_ptt")
                    return ActivationAction(
                        ActivationActionType.TRIGGER_PTT_START, "PTT"
                    )
            else:
                if self.is_ptt_active:
                    self.is_ptt_active = False
                    return ActivationAction(
                        ActivationActionType.TRIGGER_PTT_STOP, "PTT"
                    )

        # 3. Check Wake Word
        if self.mode in ("hybrid", "always_listening") and self.ww_config.get(
            "enabled", True
        ):
            # Look up threshold in correct config path
            threshold = self.full_config.get("jarvis", {}).get("threshold", 0.5)
            if context.wakeword_score > threshold:
                if context.wakeword_detected == self.ww_config.get(
                    "keyword", "hey_jarvis"
                ):
                    self._update_metric("activation_wake_word")
                    return ActivationAction(
                        ActivationActionType.TRIGGER_WAKE, "WAKE_WORD"
                    )

        return ActivationAction(ActivationActionType.NONE, "NONE")

    def _update_metric(self, name: str):
        self.metrics[name] += 1
        logger.info(f"Metric Update: {name}={self.metrics[name]}")

    def is_fullscreen(self) -> bool:
        """Detects if the foreground window is in fullscreen mode."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return False

            # Skip desktop/taskbar
            if win32gui.GetClassName(hwnd) in ("Progman", "WorkerW", "Shell_TrayWnd"):
                return False

            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

            return width >= screen_width and height >= screen_height
        except Exception as e:
            logger.error(f"Error detecting fullscreen window: {e}")
            return False

    def is_hotkey_pressed(self) -> bool:
        """Checks if the configured PTT hotkey is currently pressed."""
        try:
            # Native keyboard combination check is more robust for modifiers
            return keyboard.is_pressed(self.ptt_key)
        except Exception as e:
            # Common in non-admin or restricted environments
            logger.warning(
                f"Keyboard hotkey check failed: {e}. Disabling PTT for this tick."
            )
            return False
