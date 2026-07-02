import json
import os
from unittest.mock import patch

import pytest
import yaml

from core.execution.execution_plan import ExecutionPlan
from core.plugins.macro_manager import MacroManager


@pytest.fixture
def temp_macros_file(tmp_path):
    # Returns a path in the temporary directory to avoid writing to actual project plugins/macros.yaml
    db_file = tmp_path / "macros.yaml"
    return str(db_file)


@pytest.fixture
def macro_manager(temp_macros_file):
    return MacroManager(macros_path=temp_macros_file)


@pytest.fixture
def sample_execution_plan():
    plan_dict = {
        "schema_version": "1.0",
        "type": "action",
        "intent": "test_macro_intent",
        "explanation": "Explicação da macro de teste",
        "global_risk": "safe",
        "steps": [
            {
                "type": "command",
                "command": "echo hello",
                "step_risk": "safe",
                "description": "Exemplo",
            }
        ],
    }
    return ExecutionPlan.from_dict(plan_dict)


# 1. Tests for create_macro_from_recent
def test_create_macro_from_recent_empty(macro_manager):
    assert macro_manager.create_macro_from_recent([]) is None


def test_create_macro_from_recent_invalid_jsons(macro_manager):
    # The current MacroManager implementation does not verify if the history is empty before calling the LLM.
    # It builds an empty history text prompt and invokes the LLM regardless. We test that it calls the LLM
    # and gracefully returns None if the LLM output is not valid JSON.
    with patch("core.plugins.macro_manager.llm_agent") as mock_llm:
        mock_llm.generate_text.return_value = "invalid response"
        result = macro_manager.create_macro_from_recent(
            ["{invalid json", "another { bad } json"]
        )
        assert result is None
        mock_llm.generate_text.assert_called_once()


def test_create_macro_from_recent_happy_path(macro_manager, sample_execution_plan):
    recent = [
        json.dumps({"intent": "first_action", "explanation": "Primeira ação"}),
        json.dumps({"intent": "second_action", "explanation": "Segunda ação"}),
    ]

    mock_llm_response = json.dumps(sample_execution_plan.to_dict())

    with patch("core.plugins.macro_manager.llm_agent") as mock_llm:
        mock_llm.generate_text.return_value = f"```json\n{mock_llm_response}\n```"

        plan = macro_manager.create_macro_from_recent(recent)

        assert plan is not None
        assert plan.intent == "test_macro_intent"
        assert plan.explanation == "Explicação da macro de teste"
        assert len(plan.steps) == 1
        assert plan.steps[0].payload["command"] == "echo hello"

        # Verify LLM was prompted
        mock_llm.generate_text.assert_called_once()


def test_create_macro_from_recent_llm_fails_gracefully(macro_manager):
    recent = [json.dumps({"intent": "some_action", "explanation": "Ação"})]

    with patch("core.plugins.macro_manager.llm_agent") as mock_llm:
        # LLM returns garbage that is not valid JSON
        mock_llm.generate_text.return_value = "Erro interno do servidor"

        plan = macro_manager.create_macro_from_recent(recent)
        assert plan is None


# 2. Tests for save_macro_as_plugin and resilience
def test_save_macro_as_plugin_happy_path(
    macro_manager, temp_macros_file, sample_execution_plan
):
    with patch("core.plugins.macro_manager.plugin_manager") as mock_pm:
        success = macro_manager.save_macro_as_plugin(sample_execution_plan)

        assert success is True
        assert os.path.exists(temp_macros_file)

        # Verify content was saved as a plugin YAML structure
        with open(temp_macros_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["name"] == "macros"
            assert len(data["commands"]) == 1
            cmd = data["commands"][0]
            assert cmd["intent"] == "test_macro_intent"
            assert cmd["description"] == "Explicação da macro de teste"
            assert cmd["risk_level"] == "safe"
            assert cmd["actions"][0]["type"] == "command"
            assert cmd["actions"][0]["command"] == "echo hello"

        # Verify plugins were reloaded
        mock_pm.load_plugins.assert_called_once()


def test_save_macro_as_plugin_appends_to_existing(
    macro_manager, temp_macros_file, sample_execution_plan
):
    # Setup pre-existing macro file
    os.makedirs(os.path.dirname(temp_macros_file), exist_ok=True)
    existing_data = {
        "name": "macros",
        "commands": [
            {
                "intent": "existing_intent",
                "description": "Existing macro",
                "phrases": ["run existing"],
                "risk_level": "safe",
                "actions": [{"type": "warp", "command": "echo existing"}],
            }
        ],
    }
    with open(temp_macros_file, "w", encoding="utf-8") as f:
        yaml.dump(existing_data, f)

    with patch("core.plugins.macro_manager.plugin_manager") as mock_pm:
        success = macro_manager.save_macro_as_plugin(sample_execution_plan)
        assert success is True

        with open(temp_macros_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert len(data["commands"]) == 2
            assert data["commands"][0]["intent"] == "existing_intent"
            assert data["commands"][1]["intent"] == "test_macro_intent"

        mock_pm.load_plugins.assert_called_once()


def test_save_macro_as_plugin_resilience_corrupted_yaml(
    macro_manager, temp_macros_file, sample_execution_plan
):
    # Setup corrupted YAML file (e.g. malformed syntax)
    os.makedirs(os.path.dirname(temp_macros_file), exist_ok=True)
    with open(temp_macros_file, "w", encoding="utf-8") as f:
        f.write(
            "commands: \n  - intent: unclosed_string\n    description: 'broken yaml ..."
        )  # broken string format

    with patch("core.plugins.macro_manager.plugin_manager") as mock_pm:
        # Saving should handle the corrupted YAML parsing exception gracefully, return False, and not crash
        success = macro_manager.save_macro_as_plugin(sample_execution_plan)
        assert success is False
        mock_pm.load_plugins.assert_not_called()


def test_save_macro_as_plugin_resilience_empty_file(
    macro_manager, temp_macros_file, sample_execution_plan
):
    # Setup empty file
    os.makedirs(os.path.dirname(temp_macros_file), exist_ok=True)
    with open(temp_macros_file, "w", encoding="utf-8") as f:
        f.write("")  # completely empty

    with patch("core.plugins.macro_manager.plugin_manager") as mock_pm:
        # Saving should initialize empty file and successfully write to it
        success = macro_manager.save_macro_as_plugin(sample_execution_plan)
        assert success is True

        with open(temp_macros_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["name"] == "macros"
            assert len(data["commands"]) == 1
            assert data["commands"][0]["intent"] == "test_macro_intent"

        mock_pm.load_plugins.assert_called_once()
