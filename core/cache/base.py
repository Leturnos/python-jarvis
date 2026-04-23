from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class LLMCacheBase(ABC):
    @abstractmethod
    def get(self, instruction: str) -> Optional[Dict[str, Any]]:
        """Retrieves a cached JSON response for the given instruction."""
        pass

    @abstractmethod
    def set(self, instruction: str, response: Dict[str, Any]) -> None:
        """Saves a JSON response for the given instruction."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clears all cached entries."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, float]:
        """Returns cache statistics (e.g. hits, misses, hit rate)."""
        pass
