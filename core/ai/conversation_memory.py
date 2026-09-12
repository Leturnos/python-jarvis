import threading
import time
from dataclasses import dataclass

from core.infra.config import config
from core.infra.logger_config import logger


@dataclass
class ConversationTurn:
    """Represents a single back-and-forth conversational interaction."""

    user_query: str
    assistant_response: str
    intent: str
    timestamp: float


class ConversationMemory:
    """Maintains a rolling window of recent conversational turns for multi-turn dialogue."""

    def __init__(self, max_turns: int | None = None) -> None:
        if max_turns is None:
            max_turns = config.get("ai", {}).get("max_conversation_turns", 5)
        self.max_turns = max_turns
        self._history: list[ConversationTurn] = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)

    def record_turn(
        self,
        user_query: str,
        assistant_response: str,
        intent: str = "chat",
    ) -> None:
        """Records a completed conversation turn thread-safely."""
        q = (user_query or "").strip()
        r = (assistant_response or "").strip()
        if not q or not r:
            return

        with self._lock:
            self._history.append(
                ConversationTurn(
                    user_query=q,
                    assistant_response=r,
                    intent=intent,
                    timestamp=time.time(),
                )
            )
            while len(self._history) > self.max_turns:
                self._history.pop(0)
            total_turns = len(self._history)

        logger.debug(
            f"ConversationMemory: Recorded turn '{q[:30]}...' -> '{r[:30]}...' (Total turns: {total_turns})"
        )

    def get_context_prompt(self, ttl_seconds: float = 1800.0) -> str:
        """Formats the active conversation history into a structured prompt block."""
        now = time.time()
        with self._lock:
            active_turns = [
                turn for turn in self._history if (now - turn.timestamp) <= ttl_seconds
            ]
            if not active_turns:
                return "Nenhuma conversa anterior recente."
            lines = []
            for turn in active_turns:
                lines.append(f'Usuário: "{turn.user_query}"')
                lines.append(f'Jarvis: "{turn.assistant_response}"')
            return "\n".join(lines)

    def get_last_turn(self) -> ConversationTurn | None:
        """Returns the most recent conversation turn, or None if history is empty."""
        with self._lock:
            return self._history[-1] if self._history else None

    def clear(self) -> None:
        """Clears all conversation turns."""
        with self._lock:
            self._history.clear()


conversation_memory = ConversationMemory()
