import pytest
from unittest.mock import MagicMock, patch
from core.dispatcher import ActionDispatcher
from core.execution_plan import ExecutionPlan, RiskLevel

@pytest.fixture
def mock_dependencies():
    with patch('core.dispatcher.history_manager') as mock_history, \
         patch('core.llm_agent.llm_agent') as mock_llm_agent, \
         patch('core.dispatcher.PromptGuard', create=True) as mock_prompt_guard, \
         patch('core.dispatcher.state_manager') as mock_state:
        
        mock_prompt_guard.sanitize_output.side_effect = lambda x: x
        
        yield {
            'history': mock_history,
            'llm_agent': mock_llm_agent,
            'prompt_guard': mock_prompt_guard,
            'state': mock_state
        }

def test_explain_last_action_no_history(mock_dependencies):
    automator = MagicMock()
    dispatcher = ActionDispatcher(config={}, automator=automator)
    
    mock_dependencies['history'].get_last_successful_json.return_value = None
    
    plan = ExecutionPlan(
        intent="explain_last_action",
        explanation="Explain",
        steps=[],
        global_risk=RiskLevel.SAFE,
        schema_version="1.1"
    )
    
    result = dispatcher.handle_plan(plan)
    
    assert result is True
    automator.speak.assert_called_with("Não encontrei nenhuma ação recente para explicar.")

def test_explain_last_action_success(mock_dependencies):
    automator = MagicMock()
    dispatcher = ActionDispatcher(config={}, automator=automator)
    
    mock_dependencies['history'].get_last_successful_json.return_value = '{"intent": "system_cmd"}'
    
    # Mock LLM response
    mock_dependencies['llm_agent'].generate_text.return_value = "Eu executei um comando do sistema."
    
    plan = ExecutionPlan(
        intent="explain_last_action",
        explanation="Explain",
        steps=[],
        global_risk=RiskLevel.SAFE,
        schema_version="1.1"
    )
    
    result = dispatcher.handle_plan(plan)
    
    assert result is True
    automator.speak.assert_called_with("Eu executei um comando do sistema.")

def test_explain_last_action_error(mock_dependencies):
    automator = MagicMock()
    dispatcher = ActionDispatcher(config={}, automator=automator)
    
    mock_dependencies['history'].get_last_successful_json.return_value = '{"intent": "system_cmd"}'
    
    # Mock LLM response to raise exception
    mock_dependencies['llm_agent'].generate_text.side_effect = Exception("API error")
    
    plan = ExecutionPlan(
        intent="explain_last_action",
        explanation="Explain",
        steps=[],
        global_risk=RiskLevel.SAFE,
        schema_version="1.1"
    )
    
    result = dispatcher.handle_plan(plan)
    
    assert result is True
    automator.speak.assert_called_with("Tive um problema ao tentar gerar a explicação.")
