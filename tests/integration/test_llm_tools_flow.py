from unittest.mock import MagicMock, patch

from core.execution.execution_plan import StepType
from core.execution.job_queue import Job, JobType
from core.execution.worker import _handle_llm


@patch("core.ai.llm_agent.llm_agent.process_instruction")
@patch("core.ai.llm_agent.llm_agent.synthesize_tool_response")
@patch("core.tools.tool_registry.tool_registry.execute_tool")
def test_llm_tools_flow_web_search(mock_execute_tool, mock_synthesize, mock_process):
    dispatcher = MagicMock()
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

    notifier.notify.assert_any_call("Jarvis", "Pesquisando versão do Python na web")
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
