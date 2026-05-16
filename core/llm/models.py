from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    raw_response: Any = None
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    metadata: Dict[str, Any] = field(default_factory=dict)

class LLMError(Exception):
    """Base class for all LLM-related errors."""
    pass

class LLMProviderError(LLMError):
    """Raised when the LLM provider returns an error."""
    pass

class LLMAuthenticationError(LLMError):
    """Raised when authentication with the LLM provider fails."""
    pass

class LLMRateLimitError(LLMError):
    """Raised when the LLM provider's rate limit is exceeded."""
    pass
