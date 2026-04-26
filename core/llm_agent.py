import json
import os
from google import genai
from core.logger_config import logger
from core.config import config
from core.plugin_manager import plugin_manager
from core.cache import llm_cache
from core.prompt_guard import PromptGuard
from core.utils import time_it

class LLMAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"
        
    @time_it
    def process_instruction(self, text, context_commands=None):
        # 0. Prompt Injection Guard (Input validation)
        if not PromptGuard.is_input_safe(text):
            logger.warning(f"Blocked suspicious input: {text}")
            return {"type": "chat", "message": "Desculpe, não posso processar essa instrução por motivos de segurança."}

        # 1. Check cache first
        cached_response = llm_cache.get(text)
        if cached_response:
            logger.info(f"Using cached LLM response for: '{text}'")
            return PromptGuard.sanitize_output(cached_response)

        # 2. Cache miss, prepare prompt
        commands_list = ", ".join(context_commands) if context_commands else "Nenhum comando mapeado."
        
        intents = plugin_manager.get_intents()
        if intents:
            intents_list = []
            for i in intents:
                phrases_str = f" | Frases: {', '.join(i['phrases'])}" if i.get('phrases') else ""
                intents_list.append(f"        - Intent: '{i['intent']}' | Descrição: {i['description']}{phrases_str} | Risco: {i['risk_level']}")
            intents_str = "\n".join(intents_list)
        else:
            intents_str = "        Nenhum comando de plugin carregado."

        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        O usuário falou: "{text}"
        
        Comandos de Plugins disponíveis:
{intents_str}
        
        Outros comandos locais: [{commands_list}]
        
        Sua tarefa é decidir se o usuário quer executar uma ação técnica ou apenas conversar.
        Retorne um JSON estrito seguindo um destes formatos:

        1. Se for uma AÇÃO mapeada em um Plugin:
        {{
            "type": "action",
            "action": "plugin",
            "intent": "NOME_DO_INTENT_AQUI",
            "risk_level": "NÍVEL_DE_RISCO_DO_INTENT"
        }}

        2. Se for uma AÇÃO genérica de sistema ou terminal (Warp):
        {{
            "type": "action",
            "action": "warp" ou "system",
            "commands": ["comando 1", "comando 2"],
            "risk_level": "safe", "dangerous" ou "blocked"
        }}

        3. Se for um CHAT (conversa, pergunta, saudação):
        {{
            "type": "chat",
            "message": "Sua resposta curta e natural aqui."
        }}

        Tiers de risk_level:
        - "safe": Ações comuns, consultas, abrir pastas. Use como padrão para qualquer ação que não seja claramente perigosa ou bloqueada.
        - "dangerous": Fechar janelas, deletar arquivos específicos, alterar configurações do sistema.
        - "blocked": Formatar discos, deletar pastas do sistema (Windows, System32), apagar recursivamente o disco C:, ou qualquer ação catastrófica.

        Regras:
        - Se a ação corresponder a um comando de plugin, prefira o formato 1.
        - Se a ação for de terminal (Warp), use comandos bash/powershell (formato 2).
        - Se for de sistema, use comandos válidos de Windows CMD (formato 2).
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
            
            # Sanitize output before saving or returning
            json_data = PromptGuard.sanitize_output(json_data)
            
            # 3. Save to cache
            if json_data.get("type") == "action":
                llm_cache.set(text, json_data)
                
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

llm_agent = LLMAgent()
