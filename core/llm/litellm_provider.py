import litellm

from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.llm.base import BaseLLMProvider
from core.llm.models import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
)


class LiteLLMProvider(BaseLLMProvider):
    """LLM provider implementation using LiteLLM."""

    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        # LiteLLM model format is often 'provider/model' (e.g., 'gemini/gemini-pro')
        # But for some it might be different. Gemini with litellm is 'gemini/...'
        self.full_model_name = f"{provider}/{model}" if "/" not in model else model
        self._setup_auth()

    def _setup_auth(self):
        """Sets up authentication for LiteLLM."""
        key_name = f"{self.provider.upper()}_API_KEY"
        api_key = KeyringManager.get_secret("python-jarvis", key_name)

        if not api_key:
            import os

            api_key = os.getenv(key_name)
            if api_key:
                logger.info(f"{key_name} found in .env. Saving to Keyring.")
                KeyringManager.set_secret("python-jarvis", key_name, api_key)

        if not api_key:
            logger.warning(f"API key for {self.provider} ({key_name}) is missing.")
            # We don't raise here, but generate_content will fail if key is required

        # LiteLLM can use environment variables or be passed directly
        # For simplicity and thread safety in some environments, we can set env var
        import os

        os.environ[key_name] = api_key if api_key else ""

    def generate_content(
        self, prompt: str, system_instruction: str = None
    ) -> LLMResponse:
        """Generates content using LiteLLM."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            response = litellm.completion(
                model=self.full_model_name,
                messages=messages,
            )

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            return LLMResponse(
                content=content,
                raw_response=response,
                model=self.model,
                provider=self.provider,
                usage=usage,
            )

        except litellm.exceptions.AuthenticationError as e:
            raise LLMAuthenticationError(
                f"Authentication failed for {self.provider}: {e}"
            )
        except litellm.exceptions.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded for {self.provider}: {e}")
        except Exception as e:
            logger.error(f"LiteLLM error: {e}")
            raise LLMProviderError(f"Error from LLM provider {self.provider}: {e}")

    def get_capabilities(self) -> dict:
        """Returns provider capabilities."""
        # Simple implementation for now
        return {
            "supports_system_instructions": True,
            "provider": self.provider,
            "model": self.model,
        }
