import os

import litellm
from dotenv import load_dotenv

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

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.api_key: str | None = None
        if provider == "openrouter" and not model.startswith("openrouter/"):
            self.full_model_name = f"openrouter/{model}"
        else:
            self.full_model_name = f"{provider}/{model}" if "/" not in model else model
        self._setup_auth()

    def _setup_auth(self) -> None:
        """Sets up authentication for LiteLLM without polluting global process env."""
        key_name = f"{self.provider.upper()}_API_KEY"
        api_key = KeyringManager.get_secret("python-jarvis", key_name)

        if not api_key:
            load_dotenv()

            api_key = os.getenv(key_name)
            if api_key:
                logger.info(f"{key_name} found in .env. Saving to Keyring.")
                KeyringManager.set_secret("python-jarvis", key_name, api_key)

        if not api_key:
            logger.warning(f"API key for {self.provider} ({key_name}) is missing.")

        self.api_key = api_key if api_key else None

    def generate_content(
        self, prompt: str, system_instruction: str | None = None
    ) -> LLMResponse:
        """Generates content using LiteLLM."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key

            response = litellm.completion(
                model=self.full_model_name,
                messages=messages,
                **kwargs,
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
            ) from e
        except litellm.exceptions.RateLimitError as e:
            raise LLMRateLimitError(
                f"Rate limit exceeded for {self.provider}: {e}"
            ) from e
        except Exception as e:
            logger.error(f"LiteLLM error: {e}")
            raise LLMProviderError(
                f"Error from LLM provider {self.provider}: {e}"
            ) from e

    def get_capabilities(self) -> dict:
        """Returns provider capabilities."""
        return {
            "supports_system_instructions": True,
            "provider": self.provider,
            "model": self.model,
        }

    def test_connection(self) -> bool:
        """Verifies if the API key and provider connection are valid using a 1-token request."""
        messages = [{"role": "user", "content": "ping"}]
        try:
            kwargs = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key

            litellm.completion(
                model=self.full_model_name,
                messages=messages,
                max_tokens=1,
                **kwargs,
            )
            return True
        except Exception as e:
            logger.error(f"Active connection test failed for {self.provider}: {e}")
            return False
