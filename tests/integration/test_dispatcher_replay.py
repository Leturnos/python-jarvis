import json
from unittest.mock import MagicMock, patch

import pytest

from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    RiskLevel,
    StepType,
)
from core.persistence.history_db import HistoryManager
from core.shared.errors import BusinessError


@pytest.fixture
def replay_env(tmp_path):
    db_path = str(tmp_path / "test_replay_history.db")
    hm = HistoryManager(db_path=db_path)
    step_executor = MagicMock()
    step_executor.execute_step.return_value = True
    tts_engine = MagicMock()
    plan_builder = MagicMock()

    with (
        patch("core.execution.dispatcher.history_manager", hm),
        patch(
            "core.execution.dispatcher.PromptGuard.sanitize_output",
            side_effect=lambda x: x,
        ),
    ):
        dispatcher = ActionDispatcher(
            config={"dry_run": {"enabled": False}},
            step_executor=step_executor,
            tts_engine=tts_engine,
            plan_builder=plan_builder,
        )
        yield dispatcher, hm, step_executor, tts_engine

    hm.close()


def test_replay_after_spotify_and_weather_replays_weather_not_spotify(replay_env):
    dispatcher, _, step_executor, tts_engine = replay_env

    # 1. Execute an earlier Spotify playlist plan
    spotify_plan = ExecutionPlan(
        intent="play_query",
        explanation="Tocando playlist no Spotify",
        steps=[
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": "spotify:playlist:37i9dQZF1DXdPec7aLTmlC"},
                description="Open Spotify playlist",
            )
        ],
        global_risk=RiskLevel.SAFE,
    )
    dispatcher.last_input_text = "tocar playlist animada"
    assert dispatcher.handle_plan(spotify_plan) is True
    assert step_executor.execute_step.call_count == 1

    # 2. Execute a weather tool call (synthesized as chat)
    weather_action = {
        "type": "tool_call",
        "tool_name": "weather",
        "parameters": {"city": "Itamonte"},
        "explanation": "Consultando previsão do tempo",
        "risk_level": "safe",
    }
    with (
        patch(
            "core.execution.dispatcher.tool_registry.execute_tool",
            return_value={"success": True, "city": "Itamonte", "temperature": 22.0},
        ) as mock_exec_tool,
        patch(
            "core.execution.dispatcher.llm_agent.synthesize_tool_response",
            return_value={
                "type": "chat",
                "message": "Em Itamonte faz 22 graus com céu limpo.",
            },
        ) as mock_synth,
    ):
        assert (
            dispatcher.handle_tool_call("qual a previsão do tempo", weather_action)
            is True
        )
        assert mock_exec_tool.call_count == 1
        assert mock_synth.call_count == 1

        # 3. User says "repete": must replay weather, NOT Spotify
        assert dispatcher.dispatch("repete") is True
        assert mock_exec_tool.call_count == 2
        mock_exec_tool.assert_called_with("weather", city="Itamonte")
        assert step_executor.execute_step.call_count == 1
        tts_engine.speak.assert_called_with("Em Itamonte faz 22 graus com céu limpo.")


def test_replay_chat_command(replay_env):
    dispatcher, _, step_executor, tts_engine = replay_env

    old_plan = ExecutionPlan(
        intent="abrir_spotify",
        explanation="Abrir Spotify",
        steps=[
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": "spotify:"},
            )
        ],
        global_risk=RiskLevel.SAFE,
    )
    dispatcher.last_input_text = "abrir spotify"
    assert dispatcher.handle_plan(old_plan) is True

    dispatcher.last_input_text = "qual a capital do Brasil?"
    dispatcher.handle_dynamic({"type": "chat", "message": "A capital é Brasília."})

    tts_engine.speak.reset_mock()
    assert dispatcher.replay_last_command() is True

    tts_engine.speak.assert_called_once_with("A capital é Brasília.")
    assert step_executor.execute_step.call_count == 1


def test_replay_local_media_command(replay_env):
    dispatcher, _, _, tts_engine = replay_env

    with patch(
        "core.media.providers.os_controller.OSMediaController.send_command",
        return_value=True,
    ) as mock_send:
        dispatcher.last_input_text = "proxima musica"
        assert dispatcher.handle_local_media_command("media_next") is True
        assert mock_send.call_count == 1

        dispatcher.last_input_text = "repete"
        assert dispatcher.replay_last_command() is True
        assert mock_send.call_count == 2
        tts_engine.speak.assert_called_with("Próxima faixa.")


def test_get_last_successful_json_does_not_skip_null_action_json_row(tmp_path):
    hm = HistoryManager(db_path=str(tmp_path / "null_gap.db"))
    try:
        hm.log_execution(
            "tocar playlist",
            "voice",
            "play_query",
            "safe",
            "success",
            action_json=json.dumps({"intent": "play_query", "steps": []}),
        )
        hm.log_execution(
            "ir dormir",
            "voice",
            "sleep",
            "safe",
            "success",
            action_json=None,
        )

        assert hm.get_last_successful_json() is None

        dispatcher = ActionDispatcher(
            config={},
            step_executor=MagicMock(),
            tts_engine=MagicMock(),
            plan_builder=MagicMock(),
        )
        with (
            patch("core.execution.dispatcher.history_manager", hm),
            pytest.raises(BusinessError),
        ):
            dispatcher.replay_last_command()
    finally:
        hm.close()


def test_dispatch_replay_with_empty_history_handles_business_error_gracefully(
    replay_env,
):
    dispatcher, _, _, tts_engine = replay_env

    result = dispatcher.dispatch("repete")
    assert result is False
    tts_engine.speak.assert_called_once_with(
        "Não encontrei nenhuma ação recente para repetir."
    )
