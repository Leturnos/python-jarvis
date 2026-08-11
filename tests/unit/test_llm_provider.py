import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock litellm before importing provider to prevent C-extension DLL permission failure in sandbox
mock_litellm = MagicMock()


class MockTimeoutError(Exception):
    pass


class MockAPIConnectionError(Exception):
    pass


class MockAuthenticationError(Exception):
    pass


class MockRateLimitError(Exception):
    pass


mock_litellm.exceptions.Timeout = MockTimeoutError
mock_litellm.exceptions.APIConnectionError = MockAPIConnectionError
mock_litellm.exceptions.AuthenticationError = MockAuthenticationError
mock_litellm.exceptions.RateLimitError = MockRateLimitError

sys.modules["litellm"] = mock_litellm
sys.modules["litellm.exceptions"] = mock_litellm.exceptions

from core.llm.litellm_provider import LiteLLMProvider  # noqa: E402
from core.llm.models import LLMProviderError  # noqa: E402


def test_litellm_provider_configures_timeout_and_zero_retries():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")

    with patch(
        "core.llm.litellm_provider.check_internet_connection_async", return_value=True
    ):
        with patch.object(
            mock_litellm,
            "completion",
            side_effect=MockTimeoutError("Connection timed out"),
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
            )


def test_litellm_provider_fast_check_offline():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")

    with patch(
        "core.llm.litellm_provider.check_internet_connection_async", return_value=False
    ):
        with patch.object(mock_litellm, "completion") as mock_completion:
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate_content(prompt="Hello")

            mock_completion.assert_not_called()
            assert "internet" in str(exc_info.value).lower()
