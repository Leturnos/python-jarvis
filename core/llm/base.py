from abc import ABC, abstractmethod
from collections.abc import Iterator

from core.llm.models import LLMResponse


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_content(
        self, prompt: str, system_instruction: str | None = None
    ) -> LLMResponse:
        """Generates content based on a prompt and optional system instruction."""
        pass

    def stream_content(
        self, prompt: str, system_instruction: str | None = None
    ) -> Iterator[str]:
        """Streams content chunks; defaults to yielding a single full response."""
        response = self.generate_content(
            prompt=prompt, system_instruction=system_instruction
        )
        if response.content:
            yield str(response.content)

    @abstractmethod
    def get_capabilities(self) -> dict:
        """Returns the capabilities of the provider/model."""
        pass
