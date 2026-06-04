import time
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from core.infra.logger_config import logger
from core.runtime.state import JarvisState, state_manager


class JarvisUIAdapter(QObject):
    """Adapter for JarvisUI that centralizes state and emits Qt Signals."""

    # Unified visual state snapshot: dict containing status, score, volume, and state
    visual_state_updated = Signal(dict)

    def __init__(self, wakeword_name: str | list[str]) -> None:
        super().__init__()
        if isinstance(wakeword_name, list):
            self.wakeword_name = ", ".join(wakeword_name)
        else:
            self.wakeword_name = wakeword_name

        self._visual_state = {
            "status": "Initializing...",
            "score": 0.0,
            "volume": 0,
            "state": state_manager.get_state(),
        }

        # Listen to backend state changes instead of polling
        state_manager.add_callback(self._on_backend_state_change)

    def _on_backend_state_change(
        self,
        old_state: JarvisState,
        new_state: JarvisState,
        context: dict[str, Any] | None,
    ) -> None:
        self._visual_state["state"] = new_state
        self.visual_state_updated.emit(self._visual_state.copy())

    def update(
        self, status: str | None = None, score: float | None = None, volume: Any = None
    ) -> None:
        updated = False
        if status is not None:
            self._visual_state["status"] = status
            updated = True

        if score is not None:
            self._visual_state["score"] = float(score)
            updated = True

        if volume is not None:
            import numpy as np

            vol_int = int(np.abs(volume).mean() / 500 * 100)
            self._visual_state["volume"] = min(vol_int, 100)
            updated = True

        if updated:
            self.visual_state_updated.emit(self._visual_state.copy())

    def get_live(self) -> Any:
        class DummyLive:
            def __enter__(self) -> None:
                pass

            def __exit__(self, *args: Any) -> None:
                pass

            def stop(self) -> None:
                pass

        return DummyLive()


class JarvisTrayAdapter:
    """Adapter for JarvisTray backend requirements."""

    def __init__(self, notifier: Any = None) -> None:
        self.notifier = notifier
        self.mute_until = 0.0

    def set_mute(self, minutes: int) -> None:
        if minutes == 0:
            self.mute_until = 0.0
            state_manager.set_state(JarvisState.IDLE)
            logger.info("Jarvis unmuted.")
            if self.notifier:
                self.notifier.notify("Jarvis", "Welcome back! I'm listening.")
        else:
            self.mute_until = time.time() + (minutes * 60)
            state_manager.set_state(JarvisState.MUTED)
            msg = f"Jarvis is now sleeping. I'll be back at {(datetime.now() + timedelta(minutes=minutes)).strftime('%H:%M:%S')}."
            logger.info(msg)
            if self.notifier:
                self.notifier.notify("Jarvis", msg)

    def is_muted(self) -> bool:
        if self.mute_until == 0.0:
            return state_manager.get_state() in (
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.SUSPENDED,
            )
        if time.time() > self.mute_until:
            self.mute_until = 0.0
            state_manager.set_state(JarvisState.IDLE)
            logger.info("Auto-resuming: Jarvis is listening again.")
            if self.notifier:
                self.notifier.notify(
                    "Jarvis", "I'm back! Listening for 'Hey Jarvis' again."
                )
            return False
        return True
