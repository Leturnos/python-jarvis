import pytest
from unittest.mock import patch, MagicMock
from core.llm_agent import LLMAgent
from core.keyring_manager import KeyringManager

@patch("core.keyring_manager.KeyringManager.get_secret")
@patch("os.getenv")
@patch("google.genai.Client")
def test_llm_agent_initialization_with_keyring(mock_genai, mock_getenv, mock_get_secret):
    # Setup mock
    mock_get_secret.return_value = "mocked_keyring_key_123"
    mock_getenv.return_value = None
    
    # Initialize
    agent = LLMAgent()
    
    # Verify
    mock_get_secret.assert_called_with("python-jarvis", "GEMINI_API_KEY")
    mock_genai.assert_called_once()
    # Check if the first argument (api_key) to Client constructor was our mocked key
    assert mock_genai.call_args[1]['api_key'] == "mocked_keyring_key_123"

@patch("core.keyring_manager.KeyringManager.get_secret")
@patch("core.keyring_manager.KeyringManager.set_secret")
@patch("os.getenv")
@patch("google.genai.Client")
def test_llm_agent_initialization_fallback_and_migration(mock_genai, mock_getenv, mock_set_secret, mock_get_secret):
    # Keyring empty, but .env has the key
    mock_get_secret.return_value = None
    mock_getenv.return_value = "env_key_456"
    
    # Initialize
    agent = LLMAgent()
    
    # Verify migration occurred
    mock_set_secret.assert_called_once_with("python-jarvis", "GEMINI_API_KEY", "env_key_456")
    assert mock_genai.call_args[1]['api_key'] == "env_key_456"
