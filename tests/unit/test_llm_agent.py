from unittest.mock import patch

import pytest

from core.ai.llm_agent import LLMAgent
from core.infra.config import config


@pytest.fixture(autouse=True)
def mock_default_llm_config():
    """Forces the LLM active provider to be 'gemini' for unit testing."""
    llm_section = config.setdefault("llm", {})
    original_provider = llm_section.get("active_provider")
    providers = llm_section.setdefault("providers", {})
    gemini_config = providers.setdefault("gemini", {})
    original_model = gemini_config.get("model")

    # Force gemini
    llm_section["active_provider"] = "gemini"
    gemini_config["model"] = "gemini-2.0-flash"

    yield

    # Restore
    if original_provider is not None:
        llm_section["active_provider"] = original_provider
    else:
        llm_section.pop("active_provider", None)

    if original_model is not None:
        gemini_config["model"] = original_model
    else:
        gemini_config.pop("model", None)


@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("os.getenv")
@patch("litellm.completion")
def test_llm_agent_initialization_with_keyring(
    mock_litellm, mock_getenv, mock_get_secret
):
    # Setup mock
    mock_get_secret.return_value = "mocked_keyring_key_123"
    mock_getenv.return_value = None

    # Initialize
    LLMAgent()

    # Verify
    # LiteLLMProvider calls get_secret with GEMINI_API_KEY by default in config
    mock_get_secret.assert_called_with("python-jarvis", "GEMINI_API_KEY")


@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("core.llm.litellm_provider.KeyringManager.set_secret")
@patch("os.getenv")
@patch("litellm.completion")
def test_llm_agent_initialization_fallback_and_migration(
    mock_litellm, mock_getenv, mock_set_secret, mock_get_secret
):
    # Keyring empty, but .env has the key
    mock_get_secret.return_value = None
    mock_getenv.return_value = "env_key_456"

    # Initialize
    LLMAgent()

    # Verify migration occurred in LiteLLMProvider
    mock_set_secret.assert_called_once_with(
        "python-jarvis", "GEMINI_API_KEY", "env_key_456"
    )


@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("os.getenv")
def test_llm_agent_reinit_provider(mock_getenv, mock_get_secret):
    mock_get_secret.return_value = "dummy-key"
    mock_getenv.return_value = None

    agent = LLMAgent()
    assert agent.provider.provider == "gemini"

    # Now change configuration in config
    from core.infra.config import config

    original_provider = config["llm"].get("active_provider", "gemini")

    try:
        config["llm"]["active_provider"] = "deepseek"
        config["llm"]["providers"]["deepseek"] = {"model": "deepseek-chat"}

        # Reinit
        agent.reinit_provider()

        # Check that provider was updated
        assert agent.provider.provider == "deepseek"
        assert agent.provider.model == "deepseek-chat"
    finally:
        # Revert to gemini to avoid contaminating other tests
        config["llm"]["active_provider"] = original_provider
        agent.reinit_provider()


@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("os.getenv")
def test_llm_agent_fallback_default_model(mock_getenv, mock_get_secret):
    mock_get_secret.return_value = "dummy-key"
    mock_getenv.return_value = None

    from core.infra.config import config

    original_llm = config.get("llm", {}).copy()

    try:
        config["llm"] = {}
        agent = LLMAgent()
        assert agent.provider.provider == "openrouter"
        assert agent.provider.model == "openrouter/google/gemini-2.5-flash"
    finally:
        config["llm"] = original_llm
