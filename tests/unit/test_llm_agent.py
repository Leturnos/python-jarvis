from unittest.mock import patch

from core.ai.llm_agent import LLMAgent


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
