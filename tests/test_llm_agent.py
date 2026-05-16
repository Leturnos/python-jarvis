import pytest
from unittest.mock import patch, MagicMock
from core.llm_agent import LLMAgent

@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("os.getenv")
@patch("litellm.completion")
def test_llm_agent_initialization_with_keyring(mock_litellm, mock_getenv, mock_get_secret):
    # Setup mock
    mock_get_secret.return_value = "mocked_keyring_key_123"
    mock_getenv.return_value = None
    
    # Initialize
    agent = LLMAgent()
    
    # Verify
    # LiteLLMProvider calls get_secret with GEMINI_API_KEY by default in config
    mock_get_secret.assert_called_with("python-jarvis", "GEMINI_API_KEY")

@patch("core.llm.litellm_provider.KeyringManager.get_secret")
@patch("core.llm.litellm_provider.KeyringManager.set_secret")
@patch("os.getenv")
@patch("litellm.completion")
def test_llm_agent_initialization_fallback_and_migration(mock_litellm, mock_getenv, mock_set_secret, mock_get_secret):
    # Keyring empty, but .env has the key
    mock_get_secret.return_value = None
    mock_getenv.return_value = "env_key_456"
    
    # Initialize
    agent = LLMAgent()
    
    # Verify migration occurred in LiteLLMProvider
    mock_set_secret.assert_called_once_with("python-jarvis", "GEMINI_API_KEY", "env_key_456")
