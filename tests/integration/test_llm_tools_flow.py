from unittest.mock import MagicMock, patch

from core.execution.dispatcher import ActionDispatcher
from core.execution.execution_plan import StepType
from core.execution.job_queue import Job, JobType
from core.execution.worker import _handle_llm


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_web_search(mock_execute_tool, mock_synthesize, mock_process):
    dispatcher = MagicMock()
    dispatcher.config = {"notifications": {"voice_progress_toasts": False}}
    notifier = MagicMock()

    # Step 1: LLM returns a tool_call for web_search
    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "web_search",
        "parameters": {"query": "qual a versão mais recente do Python"},
        "explanation": "Pesquisando versão do Python na web",
        "risk_level": "safe",
    }

    # Step 2: Tool execution mock
    mock_execute_tool.return_value = {
        "success": True,
        "results": [{"title": "Python 3.13", "snippet": "Python 3.13 is released."}],
    }

    # Step 3: Synthesis returns chat
    mock_synthesize.return_value = {
        "type": "chat",
        "message": "A versão mais recente do Python é a 3.13.",
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy_audio",
        payload_text="qual a versão mais recente do Python",
    )

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True

    # Silent by default when voice_progress_toasts is disabled
    notifier.notify.assert_not_called()
    mock_execute_tool.assert_called_once_with(
        "web_search", query="qual a versão mais recente do Python"
    )
    mock_synthesize.assert_called_once()
    dispatcher.handle_dynamic.assert_called_with(
        {
            "type": "chat",
            "message": "A versão mais recente do Python é a 3.13.",
        }
    )

    # When verbose progress notifications are enabled, notifies intermediate progress
    notifier.reset_mock()
    dispatcher.config = {"notifications": {"voice_progress_toasts": True}}
    assert _handle_llm(job, dispatcher, notifier) is True
    notifier.notify.assert_any_call("Jarvis", "Pensando...")


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_git_diff_to_commit_action(
    mock_execute_tool, mock_synthesize, mock_process
):
    dispatcher = MagicMock()
    notifier = MagicMock()

    # Step 1: LLM returns tool_call for git diff
    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "git",
        "parameters": {"action": "diff", "workspace": "."},
        "explanation": "Consultando alterações git para gerar commit",
        "risk_level": "safe",
    }

    # Step 2: Tool execution returns diff
    mock_execute_tool.return_value = {
        "success": True,
        "action": "diff",
        "output": "+ add tool support in worker",
    }

    # Step 3: Synthesis returns action with git_commit step
    mock_synthesize.return_value = {
        "schema_version": "1.0",
        "type": "action",
        "intent": "git_commit",
        "explanation": "Commitar alterações com Conventional Commits",
        "global_risk": "medium",
        "steps": [
            {
                "type": "tool",
                "step_risk": "medium",
                "description": "Commitar alterações",
                "tool_name": "git",
                "parameters": {
                    "action": "commit",
                    "workspace": ".",
                    "message": "feat(tools): add tool support",
                },
            }
        ],
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy_audio",
        payload_text="gere um commit das minhas alterações",
    )

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True

    mock_execute_tool.assert_called_once_with("git", action="diff", workspace=".")
    mock_synthesize.assert_called_once()
    # Plan should be handled via dispatcher.handle_plan
    assert dispatcher.handle_plan.called
    plan = dispatcher.handle_plan.call_args[0][0]
    assert plan.intent == "git_commit"
    assert len(plan.steps) == 1
    assert plan.steps[0].type == StepType.TOOL
    assert plan.steps[0].payload["tool_name"] == "git"
    assert plan.steps[0].payload["parameters"]["action"] == "commit"
    assert (
        plan.steps[0].payload["parameters"]["message"]
        == "feat(tools): add tool support"
    )


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_weather(mock_execute_tool, mock_synthesize, mock_process):
    dispatcher = MagicMock()
    notifier = MagicMock()

    # Step 1: LLM returns tool_call for weather
    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "weather",
        "parameters": {"city": "Campinas"},
        "explanation": "Consultando clima em Campinas",
        "risk_level": "safe",
    }

    # Step 2: Tool execution mock
    mock_execute_tool.return_value = {
        "success": True,
        "city": "Campinas, São Paulo, Brasil",
        "temperature": 26.0,
        "condition": "Céu limpo",
    }

    # Step 3: Synthesis returns chat
    mock_synthesize.return_value = {
        "type": "chat",
        "message": "Em Campinas está fazendo 26°C com céu limpo.",
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy_audio",
        payload_text="como está o tempo em Campinas?",
    )

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True

    mock_execute_tool.assert_called_once_with("weather", city="Campinas")
    mock_synthesize.assert_called_once()
    assert dispatcher.handle_dynamic.called
    assert (
        dispatcher.handle_dynamic.call_args[0][0]["message"]
        == "Em Campinas está fazendo 26°C com céu limpo."
    )


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_calculator(mock_execute_tool, mock_synthesize, mock_process):
    dispatcher = MagicMock()
    notifier = MagicMock()

    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "calculator",
        "parameters": {"expression": "25 * 4"},
        "explanation": "Calculando 25 vezes 4",
        "risk_level": "safe",
    }
    mock_execute_tool.return_value = {
        "success": True,
        "operation": "calculate",
        "result": 100,
    }
    mock_synthesize.return_value = {
        "type": "chat",
        "message": "O resultado de 25 vezes 4 é 100.",
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy",
        payload_text="quanto é 25 vezes 4",
    )
    success = _handle_llm(job, dispatcher, notifier)

    assert success is True
    mock_execute_tool.assert_called_once_with("calculator", expression="25 * 4")
    mock_synthesize.assert_called_once()
    assert dispatcher.handle_dynamic.called
    assert (
        dispatcher.handle_dynamic.call_args[0][0]["message"]
        == "O resultado de 25 vezes 4 é 100."
    )


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_finance(mock_execute_tool, mock_synthesize, mock_process):
    dispatcher = MagicMock()
    notifier = MagicMock()

    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "finance",
        "parameters": {"currencies": "USD-BRL", "amount": 50},
        "explanation": "Consultando cotação do dólar",
        "risk_level": "safe",
    }
    mock_execute_tool.return_value = {
        "success": True,
        "pair": "USD-BRL",
        "bid": 5.72,
        "converted_value": 286.0,
    }
    mock_synthesize.return_value = {
        "type": "chat",
        "message": "50 dólares equivalem a 286 reais.",
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy",
        payload_text="quanto dá 50 dólares",
    )
    success = _handle_llm(job, dispatcher, notifier)

    assert success is True
    mock_execute_tool.assert_called_once_with(
        "finance", currencies="USD-BRL", amount=50
    )
    mock_synthesize.assert_called_once()
    assert dispatcher.handle_dynamic.called
    assert (
        dispatcher.handle_dynamic.call_args[0][0]["message"]
        == "50 dólares equivalem a 286 reais."
    )


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.command_resolver.CommandResolver.resolve", return_value=None)
def test_dispatcher_dispatch_tool_call(mock_resolve, mock_process):
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "calculator",
        "parameters": {"expression": "100 / 4"},
        "explanation": "Calculando divisão",
        "risk_level": "safe",
    }
    dispatcher.handle_tool_call = MagicMock(return_value=True)

    result = dispatcher.dispatch("quanto é 100 dividido por 4")
    assert result is True
    dispatcher.handle_tool_call.assert_called_once()


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.command_resolver.CommandResolver.resolve", return_value=None)
def test_dispatcher_dispatch_media(mock_resolve, mock_process):
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    mock_process.return_value = {
        "type": "media",
        "action": "PLAY_QUERY",
        "query": "lofi hip hop",
        "query_type": "mood",
        "description": "Tocando lofi",
    }
    dispatcher.handle_media = MagicMock(return_value=True)

    result = dispatcher.dispatch("tocar lofi")
    assert result is True
    dispatcher.handle_media.assert_called_once_with(mock_process.return_value)


@patch(
    "core.media.providers.os_controller.OSMediaController.send_command",
    return_value=True,
)
def test_dispatcher_dispatch_local_media(mock_os_send):
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    result = dispatcher.dispatch("pausar musica")
    assert result is True
    mock_os_send.assert_called_once()
    dispatcher.tts_engine.speak.assert_called_with("Mídia pausada.")


@patch(
    "core.media.providers.os_controller.OSMediaController.send_command",
    return_value=True,
)
def test_worker_local_media(mock_os_send):
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    notifier = MagicMock()
    job = Job(type=JobType.LLM_DYNAMIC, payload=b"dummy", payload_text="proxima musica")

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True
    mock_os_send.assert_called_once()
    dispatcher.tts_engine.speak.assert_called_with("Próxima faixa.")


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.command_resolver.CommandResolver.resolve", return_value=None)
def test_worker_voice_media_flow(mock_resolve, mock_process):
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    dispatcher.handle_media = MagicMock(return_value=True)
    notifier = MagicMock()
    media_payload = {
        "type": "media",
        "action": "PLAY_QUERY",
        "query": "queen bohemian rhapsody",
        "query_type": "entity",
    }
    mock_process.return_value = media_payload

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy_audio",
        payload_text="tocar bohemian rhapsody",
    )

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True
    dispatcher.handle_media.assert_called_once_with(media_payload)


@patch("core.media.resolver.MediaResolver.resolve_intent")
def test_dispatcher_handle_media_case_insensitive(mock_resolve_intent):
    from core.media.models import MediaAction, ResolvedMediaPlan

    mock_resolve_intent.return_value = ResolvedMediaPlan(steps=[], strategy=None)
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    dispatcher.handle_plan = MagicMock(return_value=True)

    # Test uppercase "PAUSE"
    dispatcher.handle_media({"action": "PAUSE"})
    called_intent = mock_resolve_intent.call_args[0][0]
    assert called_intent.action == MediaAction.PAUSE

    # Test "PREV" mapping to MediaAction.PREV (value "previous")
    dispatcher.handle_media({"action": "PREV"})
    called_intent = mock_resolve_intent.call_args[0][0]
    assert called_intent.action == MediaAction.PREV


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_weather_rain_direct_answer(
    mock_execute_tool, mock_synthesize, mock_process
):
    from core.ai.conversation_memory import conversation_memory
    from core.execution.dispatcher import ActionDispatcher

    conversation_memory.clear()
    dispatcher = ActionDispatcher(
        config={},
        step_executor=MagicMock(),
        tts_engine=MagicMock(),
        plan_builder=MagicMock(),
    )
    notifier = MagicMock()

    mock_process.return_value = {
        "type": "tool_call",
        "tool_name": "weather",
        "parameters": {"city": "Itamonte"},
        "explanation": "Consultando previsão de chuva para Itamonte",
        "risk_level": "safe",
    }

    mock_execute_tool.return_value = {
        "success": True,
        "city": "Itamonte, Minas Gerais, Brasil",
        "temperature": 21.0,
        "condition": "Encoberto",
        "today_forecast": {
            "max_temperature": 25.0,
            "min_temperature": 15.0,
            "rain_probability_percent": 80,
            "rain_expected": True,
            "condition_summary": "Pancadas de chuva à tarde",
        },
    }

    mock_synthesize.return_value = {
        "type": "chat",
        "message": "Provavelmente sim. O tempo está fechando e há 80% de chance de chuva à tarde em Itamonte.",
    }

    job = Job(
        type=JobType.LLM_DYNAMIC,
        payload=b"dummy_audio",
        payload_text="vai chover hoje em Itamonte?",
    )

    success = _handle_llm(job, dispatcher, notifier)
    assert success is True

    mock_execute_tool.assert_called_once_with("weather", city="Itamonte")
    mock_synthesize.assert_called_once()
    dispatcher.tts_engine.speak.assert_called_with(
        "Provavelmente sim. O tempo está fechando e há 80% de chance de chuva à tarde em Itamonte."
    )

    # Check that turn is recorded in conversation memory
    last_turn = conversation_memory.get_last_turn()
    assert last_turn is not None
    assert last_turn.user_query == "vai chover hoje em Itamonte?"
    assert "Provavelmente sim" in last_turn.assistant_response


def test_conversation_memory_integration_in_operational_context():
    from core.ai.conversation_memory import conversation_memory
    from core.ai.llm_agent import llm_agent

    conversation_memory.clear()
    conversation_memory.record_turn(
        "Como está o tempo em Itamonte?",
        "Está fechando para chuva, com 80% de probabilidade.",
        "weather",
    )

    ctx = llm_agent._get_operational_context()
    assert "conversation_history" in ctx
    assert 'Usuário: "Como está o tempo em Itamonte?"' in ctx["conversation_history"]
    assert 'Jarvis: "Está fechando para chuva' in ctx["conversation_history"]


@patch("core.execution.dispatcher.history_manager.log_execution")
@patch("core.ai.llm_agent.llm_agent._stream_with_fallback")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_handle_tool_call_streams_without_duplicate_tts_speak(
    mock_execute_tool, mock_stream, mock_log_execution
):
    from core.ai.conversation_memory import conversation_memory

    conversation_memory.clear()
    mock_execute_tool.return_value = {
        "success": True,
        "city": "Itamonte, Minas Gerais, Brasil",
        "today_forecast": {"rain_probability_percent": 60, "rain_expected": True},
    }
    mock_stream.return_value = iter(
        [
            "Sim, deve chover hoje em Itamonte. ",
            "Há 60% de chance de garoa.",
        ]
    )

    tts_mock = MagicMock()
    dispatcher = ActionDispatcher(
        config={"notifications": {"voice_progress_toasts": False}},
        step_executor=MagicMock(),
        tts_engine=tts_mock,
        plan_builder=MagicMock(),
    )

    ok = dispatcher.handle_tool_call(
        original_query="vai chover hoje?",
        action_json={
            "type": "tool_call",
            "tool_name": "weather",
            "parameters": {},
            "explanation": "Consultando clima.",
        },
    )

    assert ok is True
    tts_mock.warmup_async.assert_called()
    assert [c.args[0] for c in tts_mock.speak_stream_chunk.call_args_list] == [
        "Sim, deve chover hoje em Itamonte.",
        "Há 60% de chance de garoa.",
    ]
    # Must NOT speak the full response a second time via handle_dynamic
    tts_mock.speak.assert_not_called()
    mock_log_execution.assert_called_once()
    last_turn = conversation_memory.get_last_turn()
    assert last_turn is not None
    assert "Itamonte" in last_turn.assistant_response
