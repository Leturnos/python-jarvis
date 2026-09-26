from unittest.mock import patch

import pytest

from core.infra.keyring_manager import KeyringManager
from core.llm.litellm_provider import LiteLLMProvider
from core.llm.models import LLMAuthenticationError


def test_validate_provider_key_ignores_ambient_system_env(monkeypatch):
    # Simulate an ambient system environment variable from another app/Google SDK
    monkeypatch.setenv("GEMINI_API_KEY", "ambient_os_system_key_123")
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient_os_google_key_456")

    with patch(
        "core.infra.keyring_manager.KeyringManager.get_secret", return_value=None
    ):
        with patch(
            "core.infra.keyring_manager.KeyringManager.set_secret"
        ) as mock_set_secret:
            with patch("core.infra.keyring_manager.dotenv_values", return_value={}):
                is_valid = KeyringManager.validate_provider_key("gemini")

                assert is_valid is False
                mock_set_secret.assert_not_called()


def test_validate_provider_key_migrates_only_local_dotenv():
    with patch(
        "core.infra.keyring_manager.KeyringManager.get_secret", return_value=None
    ):
        with patch(
            "core.infra.keyring_manager.KeyringManager.set_secret"
        ) as mock_set_secret:
            with patch(
                "core.infra.keyring_manager.dotenv_values",
                return_value={"GEMINI_API_KEY": "mock_local_key_789"},
            ):
                is_valid = KeyringManager.validate_provider_key("gemini")

                assert is_valid is True
                mock_set_secret.assert_called_once_with(
                    "python-jarvis", "GEMINI_API_KEY", "mock_local_key_789"
                )


def test_litellm_provider_setup_auth_ignores_ambient_system_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ambient_os_system_key_123")
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient_os_google_key_456")

    with patch(
        "core.llm.litellm_provider.KeyringManager.get_secret", return_value=None
    ):
        with patch("core.llm.litellm_provider.dotenv_values", return_value={}):
            provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")
            assert provider.api_key is None


def test_litellm_provider_generate_content_fails_without_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient_os_google_key_456")

    with patch(
        "core.llm.litellm_provider.KeyringManager.get_secret", return_value=None
    ):
        with patch("core.llm.litellm_provider.dotenv_values", return_value={}):
            provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")
            assert provider.api_key is None

            with patch("litellm.completion") as mock_completion:
                with pytest.raises(LLMAuthenticationError):
                    provider.generate_content("ping")
                mock_completion.assert_not_called()


def test_litellm_provider_test_connection_fails_without_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient_os_google_key_456")

    with patch(
        "core.llm.litellm_provider.KeyringManager.get_secret", return_value=None
    ):
        with patch("core.llm.litellm_provider.dotenv_values", return_value={}):
            provider = LiteLLMProvider(provider="gemini", model="gemini-2.5-flash")
            assert provider.api_key is None

            with patch("litellm.completion") as mock_completion:
                assert provider.test_connection() is False
                mock_completion.assert_not_called()
