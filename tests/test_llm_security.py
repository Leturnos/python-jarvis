import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.llm_agent import llm_agent

class TestLLMSecurity(unittest.TestCase):
    def setUp(self):
        # Mock the client on the global llm_agent instance
        self.original_client = llm_agent.client
        llm_agent.client = MagicMock()
        
        # Mock llm_cache to avoid cache interference
        self.original_cache = llm_agent.llm_cache if hasattr(llm_agent, 'llm_cache') else None
        # llm_agent imports llm_cache from core.cache
        from core.llm_agent import llm_cache as global_llm_cache
        self.original_cache = global_llm_cache
        self.patcher_cache = patch('core.llm_agent.llm_cache')
        self.mock_cache = self.patcher_cache.start()
        self.mock_cache.get.return_value = None # Always miss cache
        
        # Mock RateLimiter to avoid side effects
        self.patcher_rl = patch('core.llm_agent.rate_limiter')
        self.mock_rate_limiter = self.patcher_rl.start()
        self.mock_rate_limiter.check_quotas.return_value = True

    def tearDown(self):
        # Restore everything
        llm_agent.client = self.original_client
        self.patcher_cache.stop()
        self.patcher_rl.stop()

    def test_risk_level_extraction_action(self):
        # Mock response from Gemini with risk_level
        mock_response = MagicMock()
        mock_response.text = '{"type": "action", "action": "system", "commands": ["echo hi"], "risk_level": "dangerous"}'
        llm_agent.client.models.generate_content.return_value = mock_response

        result = llm_agent.process_instruction("fechar tudo")
        
        # llm_agent normalizes risk_level to global_risk
        self.assertEqual(result.get("global_risk"), "dangerous")

    def test_risk_level_defaults_to_safe(self):
        # Mock response from Gemini without risk_level
        mock_response = MagicMock()
        mock_response.text = '{"type": "action", "action": "system", "commands": ["echo hi"]}'
        llm_agent.client.models.generate_content.return_value = mock_response

        result = llm_agent.process_instruction("fale oi")
        
        self.assertEqual(result.get("global_risk"), "safe")

    def test_risk_level_invalid_defaults_to_safe(self):
        # Mock response from Gemini with invalid risk_level
        mock_response = MagicMock()
        mock_response.text = '{"type": "action", "action": "system", "commands": ["echo hi"], "risk_level": "unknown"}'
        llm_agent.client.models.generate_content.return_value = mock_response

        result = llm_agent.process_instruction("fale oi")
        
        self.assertEqual(result.get("global_risk"), "safe")

    def test_prompt_contains_risk_tiers(self):
        # This tests if the prompt being sent contains the new information
        mock_response = MagicMock()
        mock_response.text = '{"type": "chat", "message": "Olá"}'
        llm_agent.client.models.generate_content.return_value = mock_response

        llm_agent.process_instruction("oi")
        
        # Capture the call
        args, kwargs = llm_agent.client.models.generate_content.call_args
        prompt = kwargs.get('contents', '')
        
        # The prompt template uses global_risk for instructions and Risco for intent list
        self.assertIn("global_risk", prompt)
        self.assertIn("safe", prompt)
        self.assertIn("dangerous", prompt)
        self.assertIn("blocked", prompt)

    def test_rate_limiting_fallback(self):
        # Mock rate limiter to return False (quota exceeded)
        self.mock_rate_limiter.check_quotas.return_value = False
        
        result = llm_agent.process_instruction("oi")
        
        self.assertEqual(result.get("type"), "chat")
        self.assertIn("limite", result.get("message"))
        # Verify LLM was NOT called
        llm_agent.client.models.generate_content.assert_not_called()

if __name__ == '__main__':
    unittest.main()
