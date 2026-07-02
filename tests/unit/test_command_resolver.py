from unittest.mock import patch

import pytest

from core.ai.command_resolver import CommandResolver


@pytest.fixture
def mock_plugin_intents():
    return [
        {
            "intent": "open_notepad",
            "phrases": ["abrir bloco de notas", "iniciar notepad", "bloco de notas"],
        },
        {
            "intent": "clear_terminal",
            "phrases": ["limpar terminal", "limpar tela", "clear screen"],
        },
    ]


@pytest.fixture
def resolver(mock_plugin_intents):
    with patch("core.ai.command_resolver.plugin_manager") as mock_pm:
        mock_pm.get_intents.return_value = mock_plugin_intents
        yield CommandResolver()


def test_get_available_commands_map(resolver):
    commands_map = resolver.get_available_commands_map()

    # Check plugin intents and phrases are normalized (spaces replaced by underscores) and mapped correctly
    assert commands_map["abrir_bloco_de_notas"] == "open_notepad"
    assert commands_map["iniciar_notepad"] == "open_notepad"
    assert commands_map["bloco_de_notas"] == "open_notepad"
    assert commands_map["limpar_terminal"] == "clear_terminal"

    # Check system aliases are mapped correctly
    assert commands_map["repetir"] == "replay"
    assert commands_map["de_novo"] == "replay"
    assert commands_map["criar_macro"] == "create_macro"


def test_get_available_intent_names(resolver):
    intent_names = resolver.get_available_intent_names()
    assert "open_notepad" in intent_names
    assert "clear_terminal" in intent_names
    assert "replay" in intent_names
    assert "create_macro" in intent_names


@pytest.mark.parametrize(
    "input_text,expected_intent,expected_source,expected_is_system",
    [
        # Exact system match
        ("repetir", "replay", "voice_exact", True),
        ("repetir ultimo comando", "replay", "voice_exact", True),
        ("criar macro", "create_macro", "voice_exact", True),
        # Exact plugin match
        ("abrir bloco de notas", "open_notepad", "voice_exact", False),
        ("limpar terminal", "clear_terminal", "voice_exact", False),
        # Fuzzy match
        (
            "abrir bloco de nota",
            "open_notepad",
            "voice_fuzzy",
            False,
        ),  # minor spelling diff
        ("iniciar notpad", "open_notepad", "voice_fuzzy", False),  # minor spelling diff
        (
            "limpa terminal",
            "clear_terminal",
            "voice_fuzzy",
            False,
        ),  # minor spelling diff
    ],
)
def test_resolver_successful_matches(
    resolver, input_text, expected_intent, expected_source, expected_is_system
):
    result = resolver.resolve(input_text)
    assert result is not None
    assert result.intent_name == expected_intent
    assert result.source == expected_source
    assert result.is_system == expected_is_system
    if expected_source == "voice_exact":
        assert result.confidence == 1.0
    else:
        assert 0.7 <= result.confidence < 1.0


def test_resolver_no_match(resolver):
    # Completely unrelated input should fail to match
    result = resolver.resolve("quero comer pizza hoje à noite")
    assert result is None


@pytest.mark.parametrize(
    "input_text,threshold,should_match",
    [
        # "abrir notas" has a lower similarity ratio to "abrir_bloco_de_notas" (ratio ~ 0.58).
        # A threshold of 0.9 should prevent matching, while 0.5 should allow it.
        ("abrir notas", 0.9, False),
        ("abrir notas", 0.5, True),
    ],
)
def test_resolver_custom_threshold(resolver, input_text, threshold, should_match):
    result = resolver.resolve(input_text, threshold=threshold)
    if should_match:
        assert result is not None
        assert result.intent_name == "open_notepad"
    else:
        assert result is None


def test_resolver_default_threshold_from_config(resolver):
    # If threshold is None, it should import config and read from it
    mock_config_data = {"ai": {"nlp": {"fuzzy_match_threshold": 0.99}}}
    with patch("core.infra.config.config", new=mock_config_data):
        # At 0.99 threshold, "abrir bloco de nota" (ratio ~ 0.97) should not match.
        result = resolver.resolve("abrir bloco de nota")
        assert result is None
