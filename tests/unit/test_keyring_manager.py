from core.infra.keyring_manager import KeyringManager


def test_keyring_set_and_get():
    # Arrange
    service = "python-jarvis-test"
    username = "gemini_api"
    secret = "test-secret-123"

    # Act
    KeyringManager.set_secret(service, username, secret)
    retrieved = KeyringManager.get_secret(service, username)

    # Assert
    assert retrieved == secret

    # Cleanup
    KeyringManager.delete_secret(service, username)


def test_new_providers_capabilities():
    assert KeyringManager.check_capability("deepseek", "json_mode")
    assert KeyringManager.check_capability("deepseek", "system_instructions")
    assert KeyringManager.check_capability("openrouter", "json_mode")
    assert KeyringManager.check_capability("openrouter", "system_instructions")
    assert not KeyringManager.check_capability("deepseek", "tool_use")
