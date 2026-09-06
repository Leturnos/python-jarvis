from abc import ABC, abstractmethod
from typing import Any

from core.execution.execution_plan import RiskLevel


class BaseTool(ABC):
    """Base interface for all scoped tools in the Jarvis system."""

    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.SAFE

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Executes the tool with validated arguments.

        Returns:
            dict containing at least 'success': bool, plus result or error payload.
        """
        pass

    def get_parameters_schema(self) -> dict[str, Any]:
        """Returns JSON-schema formatted parameter descriptions for LLM prompts."""
        return {"type": "object", "properties": {}}
