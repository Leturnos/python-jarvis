import threading
from collections.abc import Callable
from enum import Enum, auto
from typing import Any

from core.infra.logger_config import logger


class JarvisState(Enum):
    """Enumeration of all possible logical states for the Jarvis assistant.

    States:
        IDLE: Waiting for a wake word detection.
        LISTENING: Actively recording a voice command after wake word detection.
        THINKING: Processing the command (e.g., STT transcription or LLM analysis).
        CONFIRMING_DRY_RUN: Waiting for user approval (voice or UI) for a planned action.
        EXECUTING: Performing the steps of an execution plan.
        COOLDOWN: A brief pause after speech feedback to prevent self-triggering.
        MUTED: The system is manually muted by the user.
        SLEEPING: Deep sleep mode (unloaded models).
        SUSPENDED: Auto-suspended (e.g., fullscreen context).
        ERROR: A temporary failure state.
    """

    IDLE = auto()  # Waiting for Wake Word
    LISTENING = auto()  # Wake word detected, recording command
    THINKING = auto()  # Processing (STT / LLM)
    CONFIRMING_DRY_RUN = auto()  # Waiting for user approval
    EXECUTING = auto()  # Executing automation
    COOLDOWN = auto()  # Short pause after speaking
    MUTED = auto()  # Muted
    SLEEPING = auto()  # Sleeping (Unloaded models)
    SUSPENDED = auto()  # Auto-suspended
    ERROR = auto()  # Error state


class StateManager:
    """Thread-safe manager for the system's global state and context.

    The StateManager acts as the single source of truth for the assistant's
    current logical state. it enforces valid state transitions and notifies
    registered callbacks of any changes.

    Attributes:
        _state (JarvisState): The current state.
        _context (dict): Arbitrary metadata associated with the current state (e.g., the current plan).
        _callbacks (list): A list of functions to be called on every state change.
    """

    def __init__(self) -> None:
        """Initializes the StateManager with the IDLE state and empty context."""
        self._state = JarvisState.IDLE
        self._context: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._callbacks: list[
            Callable[[JarvisState, JarvisState, dict[str, Any]], None]
        ] = []

        # Define allowed transitions: {FROM: [TO]}
        self._allowed_transitions = {
            JarvisState.IDLE: [
                JarvisState.LISTENING,
                JarvisState.THINKING,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.SUSPENDED,
                JarvisState.EXECUTING,
            ],
            JarvisState.LISTENING: [
                JarvisState.THINKING,
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.ERROR,
            ],
            JarvisState.THINKING: [
                JarvisState.EXECUTING,
                JarvisState.CONFIRMING_DRY_RUN,
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.ERROR,
            ],
            JarvisState.CONFIRMING_DRY_RUN: [
                JarvisState.EXECUTING,
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.ERROR,
            ],
            JarvisState.EXECUTING: [
                JarvisState.IDLE,
                JarvisState.ERROR,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.COOLDOWN,
            ],
            JarvisState.COOLDOWN: [
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
                JarvisState.SUSPENDED,
            ],
            JarvisState.MUTED: [JarvisState.IDLE, JarvisState.SLEEPING],
            JarvisState.SLEEPING: [JarvisState.IDLE],
            JarvisState.SUSPENDED: [
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
            ],
            JarvisState.ERROR: [
                JarvisState.IDLE,
                JarvisState.MUTED,
                JarvisState.SLEEPING,
            ],
        }

    def get_state(self) -> JarvisState:
        """Returns the current JarvisState in a thread-safe manner.

        Returns:
            JarvisState: The current system state.
        """
        with self._lock:
            return self._state

    def get_context(self) -> dict[str, Any]:
        """Returns a copy of the current state context dictionary.

        Returns:
            Dict[str, Any]: A copy of the current context.
        """
        with self._lock:
            return self._context.copy()

    def set_state(
        self, new_state: JarvisState, context: dict[str, Any] | None = None
    ) -> None:
        """Attempts to change the system state and updates the context.

        This method validates the transition against the internal allowed_transitions
        map. If a transition is invalid, it logs a warning but proceeds (to ensure
        the system doesn't get stuck, though this behavior can be configured).
        Registered callbacks are notified after the state change.

        Args:
            new_state (JarvisState): The target state to transition to.
            context (Optional[Dict[str, Any]]): New metadata for the state. If None,
                the context is cleared (unless new_state == old_state).
        """
        with self._lock:
            old_state = self._state

            if new_state == old_state:
                if context is not None:
                    self._context.update(context)
                return

            # Transition validation
            allowed = self._allowed_transitions.get(old_state, [])
            if new_state not in allowed:
                logger.warning(
                    f"Invalid transition attempt: {old_state.name} -> {new_state.name}"
                )
                # Optional: Block or allow with warning. Following the plan, we allow but log.
                # return # Uncomment to block invalid transitions

            self._state = new_state
            if context is not None:
                self._context = context
            else:
                self._context = {}

            logger.info(
                f"State Change: {old_state.name} -> {new_state.name} | Context: {self._context}"
            )

            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(old_state, new_state, self._context)
                except Exception as e:
                    logger.error(f"Error in state callback: {e}")

    def add_callback(
        self, callback: Callable[[JarvisState, JarvisState, dict[str, Any]], None]
    ) -> None:
        """Registers a callback function to be notified of state changes.

        The callback must accept three arguments: old_state, new_state, and context.

        Args:
            callback (Callable): The callback function to register.
        """
        with self._lock:
            self._callbacks.append(callback)


# Singleton for global access
state_manager = StateManager()
