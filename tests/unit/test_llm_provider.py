from unittest.mock import patch

import litellm
import pytest

from core.llm.litellm_provider import LiteLLMProvider
from core.llm.models import LLMProviderError


def test_litellm_provider_configures_timeout_and_zero_retries():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")
    provider.api_key = "mock_test_key"

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
    provider.api_key = "mock_test_key"

    with patch(
        "core.llm.litellm_provider.check_internet_connection_async", return_value=False
    ):
        with patch("core.llm.litellm_provider.litellm.completion") as mock_completion:
            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate_content(prompt="Hello")

            mock_completion.assert_not_called()
            assert "internet" in str(exc_info.value).lower()


def test_litellm_provider_stream_content_yields_deltas():
    provider = LiteLLMProvider(provider="openrouter", model="google/gemini-2.5-flash")
    provider.api_key = "mock_test_key"

    chunks = [
        {"choices": [{"delta": {"content": "Sim, vai chover. "}}]},
        {"choices": [{"delta": {"content": ""}}]},
        {"choices": [{"delta": {"content": "Leve guarda-chuva."}}]},
    ]

    with (
        patch(
            "core.llm.litellm_provider.check_internet_connection_async",
            return_value=True,
        ),
        patch(
            "core.llm.litellm_provider.litellm.completion",
            return_value=iter(chunks),
        ) as mock_completion,
    ):
        result = list(provider.stream_content(prompt="Vai chover?"))

    assert result == ["Sim, vai chover. ", "Leve guarda-chuva."]
    _, kwargs = mock_completion.call_args
    assert kwargs.get("stream") is True


def test_litellm_provider_stream_content_offline_guard():
    provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")
    provider.api_key = "mock_test_key"

    with (
        patch(
            "core.llm.litellm_provider.check_internet_connection_async",
            return_value=False,
        ),
        patch("core.llm.litellm_provider.litellm.completion") as mock_completion,
    ):
        with pytest.raises(LLMProviderError):
            list(provider.stream_content(prompt="Hello"))
        mock_completion.assert_not_called()
