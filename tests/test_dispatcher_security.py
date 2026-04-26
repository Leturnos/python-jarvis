import pytest
from unittest.mock import MagicMock, patch
from core.dispatcher import ActionDispatcher

@pytest.fixture
def mock_config():
    return {
        'wakewords': {
            'safe_cmd': {'action': 'system', 'risk_level': 'safe', 'commands': ['echo safe']},
            'blocked_cmd': {'action': 'system', 'risk_level': 'blocked', 'commands': ['rm -rf /']},
            'dangerous_cmd': {'action': 'system', 'risk_level': 'dangerous', 'description': 'Dangerous Action', 'commands': ['format C:']}
        }
    }

@pytest.fixture
def mock_automator():
    automator = MagicMock()
    return automator

@pytest.fixture
def dispatcher(mock_config, mock_automator):
    return ActionDispatcher(mock_config, mock_automator)

def test_check_authorization_safe(dispatcher):
    action_config = {'risk_level': 'safe'}
    assert dispatcher._check_authorization(action_config) is True

def test_check_authorization_blocked(dispatcher, mock_automator):
    action_config = {'risk_level': 'blocked'}
    assert dispatcher._check_authorization(action_config) is False
    mock_automator.speak.assert_called_with("Atenção: Ação catastrófica detectada. Comando bloqueado por segurança.")

@patch('core.dispatcher.SecurityDialog')
@patch('core.dispatcher.threading.Thread')
def test_check_authorization_dangerous_approved(mock_thread, mock_dialog_class, dispatcher, mock_automator):
    action_config = {'risk_level': 'dangerous', 'description': 'Format Drive'}
    
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.ask.return_value = True
    
    assert dispatcher._check_authorization(action_config) is True
    mock_automator.speak.assert_called()
    mock_dialog_class.assert_called_with('Format Drive')

@patch('core.dispatcher.SecurityDialog')
@patch('core.dispatcher.threading.Thread')
def test_check_authorization_dangerous_rejected(mock_thread, mock_dialog_class, dispatcher, mock_automator):
    action_config = {'risk_level': 'dangerous', 'description': 'Format Drive'}
    
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.ask.return_value = False
    
    assert dispatcher._check_authorization(action_config) is False
    mock_dialog.ask.assert_called_once()

def test_handle_integrates_security(dispatcher, mock_automator):
    # Test blocked command via handle
    dispatcher.handle('blocked_cmd')
    # Should not call system handle because it's blocked
    assert mock_automator.run_workflow.call_count == 0
    # speak should be called by _check_authorization
    mock_automator.speak.assert_any_call("Atenção: Ação catastrófica detectada. Comando bloqueado por segurança.")

def test_handle_dynamic_integrates_security(dispatcher, mock_automator):
    # Test blocked command via handle_dynamic
    action_config = {'action': 'system', 'risk_level': 'blocked', 'commands': ['rm -rf /']}
    dispatcher.handle_dynamic(action_config)
    
    # speak should be called by _check_authorization
    mock_automator.speak.assert_any_call("Atenção: Ação catastrófica detectada. Comando bloqueado por segurança.")
