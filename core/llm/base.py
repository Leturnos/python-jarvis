from abc import ABC, abstractmethod

from core.llm.models import LLMResponse


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_content(
        self, prompt: str, system_instruction: str = None
    ) -> LLMResponse:
        """Generates content based on a prompt and optional system instruction."""
        pass

    @abstractmethod
    def get_capabilities(self) -> dict:
        """Returns the capabilities of the provider/model."""
        pass
