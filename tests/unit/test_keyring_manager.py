from unittest.mock import patch

from core.infra.keyring_manager import KeyringManager


def test_keyring_set_and_get():
    # Arrange
    service = "python-jarvis-test"
    username = "gemini_api"
    secret = "test-secret-123"
    storage: dict[tuple[str, str], str] = {}

    with (
        patch(
            "keyring.set_password",
            side_effect=lambda s, u, p: storage.update({(s, u): p}),
        ),
        patch("keyring.get_password", side_effect=lambda s, u: storage.get((s, u))),
        patch(
            "keyring.delete_password",
            side_effect=lambda s, u: storage.pop((s, u), None),
        ),
    ):
        # Act
        KeyringManager.set_secret(service, username, secret)
        retrieved = KeyringManager.get_secret(service, username)

        # Assert
        assert retrieved == secret

        # Cleanup
        KeyringManager.delete_secret(service, username)
        assert KeyringManager.get_secret(service, username) is None


def test_new_providers_capabilities():
    assert KeyringManager.check_capability("deepseek", "json_mode")
    assert KeyringManager.check_capability("deepseek", "system_instructions")
    assert KeyringManager.check_capability("openrouter", "json_mode")
    assert KeyringManager.check_capability("openrouter", "system_instructions")
    assert not KeyringManager.check_capability("deepseek", "tool_use")
