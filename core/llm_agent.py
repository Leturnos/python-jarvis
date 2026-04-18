import json
import os
from google import genai
from core.logger_config import logger
from core.config import config

class LLMAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"
        
    def process_instruction(self, text, context_commands=None):
        commands_list = ", ".join(context_commands) if context_commands else "Nenhum comando mapeado."
        
        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        O usuário falou: "{text}"
        Os comandos locais disponíveis são: [{commands_list}]
        
        Sua tarefa é decidir se o usuário quer executar uma ação técnica ou apenas conversar.
        Retorne um JSON estrito seguindo um destes formatos:

        1. Se for uma AÇÃO (comando de sistema ou terminal):
        {{
            "type": "action",
            "action": "warp" ou "system",
            "commands": ["comando 1", "comando 2"],
            "risk_level": "safe", "dangerous" ou "blocked"
        }}

        2. Se for um CHAT (conversa, pergunta, saudação):
        {{
            "type": "chat",
            "message": "Sua resposta curta e natural aqui."
        }}

        Tiers de risk_level:
        - "safe": Ações comuns, consultas, abrir pastas. Use como padrão para qualquer ação que não seja claramente perigosa ou bloqueada.
        - "dangerous": Fechar janelas, deletar arquivos específicos, alterar configurações do sistema.
        - "blocked": Formatar discos, deletar pastas do sistema (Windows, System32), apagar recursivamente o disco C:, ou qualquer ação catastrófica.

        Regras:
        - Se a ação for de terminal (Warp), use comandos bash/powershell.
        - Se for de sistema, use comandos válidos de Windows CMD.
        - Retorne APENAS o JSON, sem crases markdown (```json).
        """
        
        try:
            logger.info("Sending to Gemini...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            result = response.text.strip()
            
            # Clean up markdown if Gemini ignores instructions
            if result.startswith("```json"):
                result = result[7:-3].strip()
            elif result.startswith("```"):
                result = result[3:-3].strip()
                
            json_data = json.loads(result)
            ALLOWED_RISKS = ["safe", "dangerous", "blocked"]
            if json_data.get("type") == "action":
                if json_data.get("risk_level") not in ALLOWED_RISKS:
                    json_data["risk_level"] = "safe"
            
            logger.info(f"LLM Response: {json_data}")
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

llm_agent = LLMAgent()
