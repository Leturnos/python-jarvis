import logging
from typing import Any

import keyboard
from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


def normalize_hotkey_parts(names: list[str]) -> str:
    """Normalizes a collection of physical key names into canonical Jarvis hotkey syntax.

    Example:
        ['left ctrl', 'left alt'] -> 'ctrl+alt'
        ['p', 'left shift', 'left ctrl'] -> 'ctrl+shift+p'
        ['space', 'alt'] -> 'alt+space'
    """
    modifier_order = ["ctrl", "alt", "shift", "win"]
    modifiers: list[str] = []
    regular_keys: list[str] = []

    for name in names:
        n = name.lower().strip()
        if n in ("left ctrl", "right ctrl", "control", "ctrl"):
            if "ctrl" not in modifiers:
                modifiers.append("ctrl")
        elif n in ("left alt", "right alt", "menu", "alt"):
            if "alt" not in modifiers:
                modifiers.append("alt")
        elif n in ("left shift", "right shift", "shift"):
            if "shift" not in modifiers:
                modifiers.append("shift")
        elif n in ("left windows", "right windows", "win", "windows"):
            if "win" not in modifiers:
                modifiers.append("win")
        elif n == "alt gr":
            if "alt" not in modifiers:
                modifiers.append("alt")
        else:
            if n and n not in regular_keys:
                regular_keys.append(n)

    sorted_mods = [m for m in modifier_order if m in modifiers]
    return "+".join(sorted_mods + regular_keys)


class HotkeyRecorder(QObject):
    """Listens for physical keyboard events to record hotkey combinations with a countdown timer."""

    hotkey_captured = Signal(str)  # Emits final combination, e.g. "ctrl+alt"
    live_preview = Signal(
        str
    )  # Emits live combination as keys are pressed, e.g. "ctrl+alt"
    tick = Signal(int)  # Emits remaining seconds: 5, 4, 3, 2, 1
    cancelled = Signal()  # Emits when cancelled by user or Esc
    timeout = Signal()  # Emits when 5 seconds elapse without keypress

    # Internal signal for thread-safe event marshalling
    _key_signal = Signal(str, str)  # (key_name, event_type)

    def __init__(
        self, countdown_seconds: int = 5, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.countdown_seconds = countdown_seconds
        self._seconds_left = countdown_seconds
        self._hook: Any = None
        self._is_active = False

        self._pressed_keys: set[str] = set()
        self._combination: set[str] = set()

        self._key_signal.connect(self._on_key_event)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)

    @property
    def is_active(self) -> bool:
        return self._is_active

    def start(self) -> None:
        """Starts listening for hotkeys and begins the countdown."""
        if self._is_active:
            self.cancel()

        self._pressed_keys.clear()
        self._combination.clear()
        self._seconds_left = self.countdown_seconds
        self._is_active = True

        try:
            self._hook = keyboard.hook(self._hook_callback)
        except Exception as e:
            logger.error(f"Failed to install keyboard hook for hotkey recording: {e}")
            self._is_active = False
            self.cancelled.emit()
            return

        self._timer.start()
        self.tick.emit(self._seconds_left)

    def _hook_callback(self, event: keyboard.KeyboardEvent) -> None:
        if self._is_active and event.name:
            self._key_signal.emit(event.name, event.event_type)

    def _on_key_event(self, name: str, event_type: str) -> None:
        if not self._is_active:
            return

        key_lower = name.lower().strip()
        if key_lower in ("esc", "escape"):
            self.cancel()
            return

        if event_type == "down":
            self._pressed_keys.add(key_lower)
            self._combination.update(self._pressed_keys)
            preview = normalize_hotkey_parts(list(self._combination))
            self.live_preview.emit(preview)
        elif event_type == "up":
            self._pressed_keys.discard(key_lower)
            if self._combination and len(self._pressed_keys) == 0:
                # All keys released, lock in the hotkey!
                final_hotkey = normalize_hotkey_parts(list(self._combination))
                self.stop()
                self.hotkey_captured.emit(final_hotkey)

    def _on_timer_tick(self) -> None:
        self._seconds_left -= 1
        if self._seconds_left > 0:
            self.tick.emit(self._seconds_left)
        else:
            self.stop()
            self.timeout.emit()

    def cancel(self) -> None:
        """Explicitly cancels recording."""
        self.stop()
        self.cancelled.emit()

    def stop(self) -> None:
        """Stops timer and unhooks keyboard."""
        self._is_active = False
        self._timer.stop()
        if self._hook:
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None
