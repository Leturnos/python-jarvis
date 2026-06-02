from abc import ABC, abstractmethod
from typing import Any


class LLMCacheBase(ABC):
    @abstractmethod
    def get(self, instruction: str) -> dict[str, Any] | None:
        """Retrieves a cached JSON response for the given instruction."""
        pass

    @abstractmethod
    def set(self, instruction: str, response: dict[str, Any]) -> None:
        """Saves a JSON response for the given instruction."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clears all cached entries."""
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, float]:
        """Returns cache statistics (e.g. hits, misses, hit rate)."""
        pass
