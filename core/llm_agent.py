import json
import os
from google import genai
from core.logger_config import logger
from core.config import config
from core.plugin_manager import plugin_manager
from core.cache import llm_cache
from core.prompt_guard import PromptGuard
from core.utils import time_it
from core.rate_limiter import rate_limiter
from core.errors import TechnicalError

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
        Você é o Jarvis, um assistente de terminal no Windows. Seu objetivo é ajudar o usuário com automações seguras.
        O usuário falou: "{text}"
        
        Comandos de Plugins disponíveis:
{intents_str}
        
        Outros comandos locais: [{commands_list}]

        Ações de Sistema Especiais:
        - Intent: 'replay' | Descrição: Repete a última ação bem sucedida.
        - Intent: 'create_macro' | Descrição: Cria uma macro (sequência de comandos) a partir das últimas ações. Aceita parâmetro 'n' (ex: 'n': 3).

        Sua tarefa é decidir se o usuário quer executar uma ação técnica ou apenas conversar.
        Retorne um JSON estrito seguindo um destes formatos:

        1. Se for uma AÇÃO (Plugin, Sistema, Terminal, Apps):
        {{
            "schema_version": "1.0",
            "type": "action",
            "intent": "nome_curto_da_intencao",
            "explanation": "Uma frase curta explicando o que você vai fazer em termos humanos.",
            "global_risk": "safe", "low", "medium", "high", "dangerous" ou "blocked",
            "steps": [
                {{
                    "type": "command", "open_app", "write", "navigate" ou "wait",
                    "command": "o comando se for type command",
                    "target": "caminho ou app se for type open_app ou navigate",
                    "text": "texto se for type write",
                    "duration": 1.0,
                    "step_risk": "mesmos níveis do global_risk",
                    "description": "descrição curta deste passo"
                }}
            ]
        }}

        2. Se for um CHAT (conversa, pergunta, saudação):
        {{
            "type": "chat",
            "message": "Sua resposta curta e natural aqui."
        }}

        Tiers de Risco:
        - "safe": Consultas, abrir pastas, git status. (Default)
        - "low": Abrir apps, navegar em pastas.
        - "medium": Criar pastas/arquivos, rodar testes, git commit.
        - "high": Deletar arquivos específicos, alterar configurações.
        - "dangerous": Matar processos, deletar pastas.
        - "blocked": Formatar discos, deletar pastas do sistema, apagar disco C:.

        Regras:
        - SEMPRE retorne um "explanation" humano para ações.
        - Se a ação corresponder a um comando de plugin, use type "command" ou o tipo mais adequado dentro dos steps.
        - Retorne APENAS o JSON, sem markdown.
        """
        
        # Check Rate Limits
        if not rate_limiter.check_quotas():
            logger.info("Rate limit reached. Returning fallback message.")
            return {
                "type": "chat",
                "message": "Atingi o limite de uso de IA por hoje.\nPosso continuar com comandos locais, ou você pode tentar novamente em algumas horas."
            }

        try:
            logger.info("Sending to Gemini...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            result = response.text.strip()
            
            # Clean up markdown
            if result.startswith("```json"):
                result = result[7:-3].strip()
            elif result.startswith("```"):
                result = result[3:-3].strip()
                
            json_data = json.loads(result)
            
            if json_data.get("type") == "action":
                # Basic normalization for legacy compatibility if needed
                if "risk_level" in json_data and "global_risk" not in json_data:
                    json_data["global_risk"] = json_data["risk_level"]
                
                ALLOWED_RISKS = ["safe", "low", "medium", "high", "dangerous", "blocked"]
                if json_data.get("global_risk") not in ALLOWED_RISKS:
                    json_data["global_risk"] = "safe"
            
            logger.info(f"LLM Response Parsed: {json_data}")

            # Log usage
            total_tokens = 0
            if hasattr(response, 'usage_metadata') and hasattr(response.usage_metadata, 'total_token_count'):
                total_tokens = response.usage_metadata.total_token_count
            rate_limiter.log_usage(token_count=total_tokens)

            # Sanitize output before saving or returning
            json_data = PromptGuard.sanitize_output(json_data)
            
            # 3. Save to cache
            if json_data.get("type") == "action":
                llm_cache.set(text, json_data)
                
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            raise TechnicalError(f"LLM processing failed: {e}")

llm_agent = LLMAgent()
