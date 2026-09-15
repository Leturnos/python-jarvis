from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    RiskLevel,
    StepType,
)


@pytest.fixture
def mock_config():
    return {
        "dry_run": {
            "enabled": True,
            "bypass_for_safe_intents": True,
        },
        "security": {
            "trusted_apps": [
                {
                    "name": "spotify",
                    "path": r"C:\Program Files\Spotify\Spotify.exe",
                    "allowed_actions": ["system_open"],
                }
            ]
        },
        "wakewords": {
            "safe_cmd": {
                "action": "system",
                "risk_level": "safe",
                "commands": ["echo safe"],
            },
            "blocked_cmd": {
                "action": "system",
                "risk_level": "blocked",
                "commands": ["rm -rf /"],
            },
            "dangerous_cmd": {
                "action": "system",
                "risk_level": "dangerous",
                "description": "Dangerous Action",
                "commands": ["format C:"],
            },
        },
    }


@pytest.fixture
def mock_tts_engine():
    tts_engine = MagicMock()
    return tts_engine


@pytest.fixture
def dispatcher(mock_config, mock_tts_engine):
    return ActionDispatcher(
        config=mock_config,
        step_executor=MagicMock(),
        tts_engine=mock_tts_engine,
        plan_builder=MagicMock(),
    )


def test_check_authorization_safe(dispatcher):
    action_config = {"risk_level": "safe"}
    assert dispatcher._check_authorization(action_config) is True


def test_check_authorization_blocked(dispatcher, mock_tts_engine):
    action_config = {"risk_level": "blocked"}
    assert dispatcher._check_authorization(action_config) is False
    mock_tts_engine.speak.assert_called_with(
        "Atenção: Ação catastrófica detectada. Comando bloqueado por segurança."
    )


@patch("core.execution.dispatcher.SecurityDialog")
def test_check_authorization_dangerous_approved(
    mock_dialog_class, dispatcher, mock_tts_engine
):
    action_config = {"risk_level": "dangerous", "description": "Format Drive"}

    mock_dialog = mock_dialog_class.return_value
    mock_dialog.ask.return_value = True

    assert dispatcher._check_authorization(action_config) is True
    mock_tts_engine.speak.assert_called()
    mock_dialog_class.assert_called_with("Format Drive")


@patch("core.execution.dispatcher.SecurityDialog")
def test_check_authorization_dangerous_rejected(
    mock_dialog_class, dispatcher, mock_tts_engine
):
    action_config = {"risk_level": "dangerous", "description": "Format Drive"}

    mock_dialog = mock_dialog_class.return_value
    mock_dialog.ask.return_value = False

    assert dispatcher._check_authorization(action_config) is False
    mock_dialog.ask.assert_called_once()


def test_handle_integrates_security(dispatcher, mock_tts_engine):
    # Test blocked command via handle
    dispatcher.execute_plan = MagicMock()
    dispatcher.handle("blocked_cmd")
    # Should not execute plan because it's blocked
    assert dispatcher.execute_plan.call_count == 0
    # speak should be called by _check_authorization
    mock_tts_engine.speak.assert_any_call(
        "Atenção: Ação catastrófica detectada. Comando bloqueado por segurança."
    )


def test_handle_dynamic_integrates_security(dispatcher, mock_tts_engine):
    # Test blocked command via handle_dynamic
    dispatcher.execute_plan = MagicMock()
    action_config = {
        "action": "system",
        "risk_level": "blocked",
        "commands": ["rm -rf /"],
    }
    dispatcher.handle_dynamic(action_config)
    assert dispatcher.execute_plan.call_count == 0

    # speak should be called by _check_authorization
    mock_tts_engine.speak.assert_any_call(
        "Atenção: Ação catastrófica detectada. Comando bloqueado por segurança."
    )


def test_handle_plan_trusted_app_bypasses_confirmation(dispatcher):
    plan = ExecutionPlan(
        intent="media_play",
        explanation="Abrindo o Spotify",
        steps=[
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": "Spotify"},
                step_risk=RiskLevel.LOW,
            )
        ],
        global_risk=RiskLevel.LOW,
    )
    dispatcher._confirm_dry_run = MagicMock()
    dispatcher.execute_plan = MagicMock(return_value=True)

    result = dispatcher.handle_plan(plan)

    assert result is True
    assert plan.global_risk == RiskLevel.SAFE
    assert dispatcher._confirm_dry_run.call_count == 0
    dispatcher.execute_plan.assert_called_once()


def test_handle_plan_untrusted_app_requires_confirmation(dispatcher):
    plan = ExecutionPlan(
        intent="open_untrusted",
        explanation="Abrindo app desconhecido",
        steps=[
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": "untrusted_app"},
                step_risk=RiskLevel.LOW,
            )
        ],
        global_risk=RiskLevel.LOW,
    )
    dispatcher._confirm_dry_run = MagicMock(return_value=True)
    dispatcher.execute_plan = MagicMock(return_value=True)

    result = dispatcher.handle_plan(plan)

    assert result is True
    assert plan.global_risk == RiskLevel.LOW
    dispatcher._confirm_dry_run.assert_called_once_with(plan)
    dispatcher.execute_plan.assert_called_once()


def test_execute_plan_resets_state_to_idle(dispatcher: Any) -> None:
    from core.runtime.state import JarvisState, state_manager

    plan = ExecutionPlan(
        intent="open_trusted",
        explanation="Abrindo app seguro",
        steps=[
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": "Spotify"},
                step_risk=RiskLevel.SAFE,
            )
        ],
        global_risk=RiskLevel.SAFE,
    )

    dispatcher.step_executor.execute_step = MagicMock(return_value=True)

    success = dispatcher.execute_plan(plan)

    assert success is True
    assert state_manager.get_state() == JarvisState.IDLE


def test_dispatch_resets_state_to_idle(dispatcher: Any) -> None:
    from core.runtime.state import JarvisState, state_manager

    with patch("core.ai.llm_agent.llm_agent.process_instruction") as mock_process:
        mock_process.return_value = {
            "type": "action",
            "intent": "open_app",
            "explanation": "Abrindo Spotify",
            "steps": [
                {
                    "type": "open_app",
                    "payload": {"target": "Spotify"},
                    "step_risk": "safe",
                }
            ],
            "global_risk": "safe",
        }
        dispatcher.step_executor.execute_step = MagicMock(return_value=True)

        success = dispatcher.dispatch("abrir spotify")

        assert success is True
        mock_process.assert_called_once_with("abrir spotify")
        assert state_manager.get_state() == JarvisState.IDLE


def test_handle_plan_system_sleep_intent(dispatcher: Any) -> None:
    from core.runtime.state import JarvisState, state_manager

    plan = ExecutionPlan(
        intent="sleep",
        explanation="Indo dormir.",
    )

    with (
        patch("core.execution.dispatcher.history_manager.log_execution") as mock_log,
        patch("core.execution.dispatcher.conversation_memory.record_turn") as mock_mem,
    ):
        result = dispatcher.handle_plan(plan)

    assert result is True
    assert state_manager.get_state() == JarvisState.SLEEPING
    dispatcher.tts_engine.speak.assert_called_with(
        "Indo dormir. Use o atalho ou a bandeja para me acordar."
    )
    mock_log.assert_called_once()
    mock_mem.assert_called_once()


def test_handle_plan_system_mute_intent(dispatcher: Any) -> None:
    from core.runtime.state import JarvisState, state_manager

    plan = ExecutionPlan(
        intent="mute",
        explanation="Silenciar.",
    )

    with (
        patch("core.execution.dispatcher.history_manager.log_execution") as mock_log,
        patch("core.execution.dispatcher.conversation_memory.record_turn") as mock_mem,
    ):
        result = dispatcher.handle_plan(plan)

    assert result is True
    assert state_manager.get_state() == JarvisState.MUTED
    dispatcher.tts_engine.speak.assert_called_with("Silenciado.")
    mock_log.assert_called_once()
    mock_mem.assert_called_once()


def test_dispatch_sleep_and_mute_commands(dispatcher: Any) -> None:
    from core.runtime.state import JarvisState, state_manager

    with (
        patch("core.execution.dispatcher.history_manager.log_execution"),
        patch("core.execution.dispatcher.conversation_memory.record_turn"),
    ):
        success_sleep = dispatcher.dispatch("ir dormir")
        assert success_sleep is True
        assert state_manager.get_state() == JarvisState.SLEEPING

        success_mute = dispatcher.dispatch("silenciar")
        assert success_mute is True
        assert state_manager.get_state() == JarvisState.MUTED
