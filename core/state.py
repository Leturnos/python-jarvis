from enum import Enum, auto
import threading
from typing import Dict, Any, Optional, Callable, List
from core.logger_config import logger

class JarvisState(Enum):
    IDLE = auto()               # Waiting for Wake Word
    LISTENING = auto()          # Wake word detected, recording command
    THINKING = auto()           # Processing (STT / LLM)
    CONFIRMING_DRY_RUN = auto() # Waiting for user approval
    EXECUTING = auto()          # Executing automation
    MUTED = auto()              # Muted/Sleeping
    ERROR = auto()              # Error state

class StateManager:
    def __init__(self):
        self._state = JarvisState.IDLE
        self._context: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[JarvisState, JarvisState, Dict[str, Any]], None]] = []

        # Define allowed transitions: {FROM: [TO]}
        self._allowed_transitions = {
            JarvisState.IDLE: [JarvisState.LISTENING, JarvisState.THINKING, JarvisState.MUTED, JarvisState.EXECUTING],
            JarvisState.LISTENING: [JarvisState.THINKING, JarvisState.IDLE, JarvisState.MUTED, JarvisState.ERROR],
            JarvisState.THINKING: [JarvisState.EXECUTING, JarvisState.CONFIRMING_DRY_RUN, JarvisState.IDLE, JarvisState.MUTED, JarvisState.ERROR],
            JarvisState.CONFIRMING_DRY_RUN: [JarvisState.EXECUTING, JarvisState.IDLE, JarvisState.MUTED],
            JarvisState.EXECUTING: [JarvisState.IDLE, JarvisState.ERROR, JarvisState.MUTED],
            JarvisState.MUTED: [JarvisState.IDLE],
            JarvisState.ERROR: [JarvisState.IDLE, JarvisState.MUTED]
        }

    def get_state(self) -> JarvisState:
        with self._lock:
            return self._state

    def get_context(self) -> Dict[str, Any]:
        with self._lock:
            return self._context.copy()

    def set_state(self, new_state: JarvisState, context: Optional[Dict[str, Any]] = None):
        with self._lock:
            old_state = self._state
            
            if new_state == old_state:
                if context is not None:
                    self._context.update(context)
                return

            # Transition validation
            allowed = self._allowed_transitions.get(old_state, [])
            if new_state not in allowed:
                logger.warning(f"Invalid transition attempt: {old_state.name} -> {new_state.name}")
                # Optional: Block or allow with warning. Following the plan, we allow but log.
                # return # Uncomment to block invalid transitions

            self._state = new_state
            if context is not None:
                self._context = context
            else:
                self._context = {}

            logger.info(f"State Change: {old_state.name} -> {new_state.name} | Context: {self._context}")
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(old_state, new_state, self._context)
                except Exception as e:
                    logger.error(f"Error in state callback: {e}")

    def add_callback(self, callback: Callable[[JarvisState, JarvisState, Dict[str, Any]], None]):
        with self._lock:
            self._callbacks.append(callback)

# Singleton for global access
state_manager = StateManager()
