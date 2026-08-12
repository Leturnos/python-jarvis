from unittest.mock import patch

import litellm
import pytest

from core.llm.litellm_provider import LiteLLMProvider
from core.llm.models import LLMProviderError


def test_litellm_provider_configures_timeout_and_zero_retries():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")

    with patch(
        "core.llm.litellm_provider.check_internet_connection_async", return_value=True
    ):
        with patch(
            "core.llm.litellm_provider.litellm.completion",
            side_effect=litellm.exceptions.Timeout(
                "Connection timed out", model="gemini", llm_provider="gemini"
            ),
        ) as mock_completion:
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate_content(prompt="Hello", system_instruction="Test")

            mock_completion.assert_called_once()
            _, kwargs = mock_completion.call_args
            assert kwargs.get("timeout") == 5.0
            assert kwargs.get("num_retries") == 0
            assert (
                "conect" in str(exc_info.value).lower()
                or "internet" in str(exc_info.value).lower()
                or "timed out" in str(exc_info.value).lower()
            )


def test_litellm_provider_fast_check_offline():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")

    with patch(
        "core.llm.litellm_provider.check_internet_connection_async", return_value=False
    ):
        with patch("core.llm.litellm_provider.litellm.completion") as mock_completion:
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate_content(prompt="Hello")

            mock_completion.assert_not_called()
            assert "internet" in str(exc_info.value).lower()
