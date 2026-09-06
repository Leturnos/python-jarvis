import json
import threading
from typing import Any

from core.ai.prompt_guard import PromptGuard
from core.cache import llm_cache
from core.infra.config import config
from core.infra.logger_config import logger
from core.llm import LiteLLMProvider, LLMError
from core.persistence.history_db import history_manager
from core.plugins.plugin_manager import plugin_manager
from core.runtime.rate_limiter import rate_limiter
from core.shared.constants import DEFAULT_MODELS, DEFAULT_PROVIDER
from core.shared.errors import TechnicalError
from core.shared.utils import time_it
from core.tools.tool_registry import tool_registry


class LLMAgent:
    """Interface for the AI reasoning engine.

    The LLMAgent is responsible for interpreting natural language instructions from
    the user and deciding whether they represent a conversational intent (chat) or
    a technical automation request (action). It uses a pluggable LLM provider.

    Attributes:
        provider (BaseLLMProvider): The LLM provider instance.
    """

    def __init__(self) -> None:
        """Initializes the LLM provider based on config."""
        self._lock = threading.Lock()
        self._init_provider()

    def _init_provider(self) -> None:
        llm_config = config.get("llm", {})
        active_provider = llm_config.get("active_provider", DEFAULT_PROVIDER)

        provider_config = llm_config.get("providers", {}).get(active_provider, {})
        model_name = provider_config.get("model")

        if not model_name:
            model_name = DEFAULT_MODELS.get(active_provider, "gemini-2.5-flash")
            logger.warning(
                f"Model configuration for active provider '{active_provider}' is missing. "
                f"Falling back to default model: '{model_name}'"
            )

        logger.info(
            f"Initializing LLMAgent with provider: {active_provider}, model: {model_name}"
        )
        self.provider = LiteLLMProvider(provider=active_provider, model=model_name)

    def reinit_provider(self) -> None:
        """Reinitializes the LLM provider instance dynamically when settings change."""
        with self._lock:
            self._init_provider()

    def _execute_with_fallback(self, prompt: str) -> Any:
        """Executes LLM request with automatic multi-provider fallback on failure."""
        llm_cfg = config.get("llm", {})
        configured_providers = list(llm_cfg.get("providers", {}).keys())
        default_order = ["gemini", "openai", "anthropic", "deepseek", "openrouter"]

        candidates = [self.provider.provider]
        for p in configured_providers + default_order:
            if p not in candidates:
                candidates.append(p)

        last_err = None
        for prov_name in candidates:
            try:
                if prov_name == self.provider.provider:
                    prov_instance = self.provider
                else:
                    logger.info(f"Attempting fallback LLM Provider '{prov_name}'...")
                    model_name = llm_cfg.get("providers", {}).get(prov_name, {}).get(
                        "model"
                    ) or DEFAULT_MODELS.get(prov_name, "gemini-2.5-flash")
                    prov_instance = LiteLLMProvider(
                        provider=prov_name, model=model_name
                    )

                logger.info(f"Sending to LLM Provider ({prov_name})...")
                return prov_instance.generate_content(prompt=prompt)
            except Exception as e:
                logger.warning(f"LLM Provider '{prov_name}' failed: {e}")
                last_err = e

        raise TechnicalError(f"All LLM providers failed. Last error: {last_err}")

    @time_it
    def process_instruction(
        self, text: str, context_commands: list[Any] | None = None
    ) -> dict[str, Any]:
        """Analyzes user text and returns a structured decision (action or chat).

        This method coordinates the entire AI processing pipeline:
        1. Validates input against prompt injection (PromptGuard).
        2. Checks the local SQLite cache for recurring instructions.
        3. Enforces daily and burst rate limits.
        4. Dynamically builds a system prompt including available plugins and intents.
        5. Calls the LLM provider and parses the strict JSON response.
        6. Normalizes risk levels and sanitizes the output plan.

        Args:
            text (str): The natural language instruction (transcribed or typed).
            context_commands (list, optional): List of currently mapped static wakewords.

        Returns:
            dict: A dictionary following either the 'action' or 'chat' schema.

        Raises:
            TechnicalError: If the LLM service is unavailable or returns unparseable data.
        """
        # 0. Prompt Injection Guard (Input validation)
        if not PromptGuard.is_input_safe(text):
            logger.warning(f"Blocked suspicious input: {text}")
            return {
                "type": "chat",
                "message": "Desculpe, não posso processar essa instrução por motivos de segurança.",
            }

        # 1. Check cache first
        cached_response = llm_cache.get(text)
        if cached_response:
            logger.info(f"Using cached LLM response for: '{text}'")
            history_manager.log_metric("llm_cache_hit", 1.0)
            return PromptGuard.sanitize_output(cached_response)

        history_manager.log_metric("llm_cache_hit", 0.0)

        # 2. Cache miss, prepare prompt
        commands_list = (
            ", ".join(context_commands) if context_commands else "Nenhum comando."
        )

        intents = plugin_manager.get_intents()
        if intents:
            intents_list = []
            for i in intents:
                phrases_str = (
                    f" | Frases: {', '.join(i['phrases'])}" if i.get("phrases") else ""
                )
                intents_list.append(
                    f"        - Intent: '{i['intent']}' | Descrição: "
                    f"{i['description']}{phrases_str} | Risco: {i['risk_level']}"
                )
            intents_str = "\n".join(intents_list)
        else:
            intents_str = "        Nenhum comando de plugin carregado."

        tools_desc = tool_registry.get_tools_prompt_description()

        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        Seu objetivo é ajudar o usuário com automações seguras.
        O usuário falou: "{text}"

        Comandos de Plugins disponíveis:
{intents_str}

        Outros comandos locais: [{commands_list}]

        Ações de Sistema Especiais (PRIORIDADE ALTA):
        - Intent: 'sleep' | Descrição: O usuário quer que você pare de ouvir, descanse,
          durma ou se desative temporariamente. Use este intent para comandos como
          "vá descansar", "dormir", "parar de ouvir", "desativar".
        - Intent: 'mute' | Descrição: O usuário quer silenciar você.
        - Intent: 'replay' | Descrição: Repete a última ação bem sucedida.
        - Intent: 'create_macro' | Descrição: Cria uma macro a partir das últimas ações.
        - Intent: 'explain_last_action' | Descrição: Explica o que você acabou de fazer.

        Ferramentas com Escopo Seguro Disponíveis (Tool Calling):
{tools_desc}

        Sua tarefa é decidir se o usuário quer executar uma ação técnica, chamar uma ferramenta ou conversar.
        Retorne um JSON estrito seguindo um destes formatos:

        1. Se for uma AÇÃO (Plugin, Sistema, Terminal, Apps):
        {{
            "schema_version": "1.0",
            "type": "action",
            "intent": "nome_curto_da_intencao",
            "explanation": "Uma frase explicando o que você vai fazer em termos humanos.",
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

        2. Se for um CHAT (conversa, pergunta genérica, saudação):
        {{
            "type": "chat",
            "message": "Sua resposta curta e natural aqui."
        }}

        3. Se for uma MÍDIA (tocar música, pausar, pular no Spotify ou sistema):
        {{
            "type": "media",
            "action": "PLAY_QUERY",
            "query": "nome da música, artista ou humor",
            "query_type": "mood",
            "description": "Tocando sua música"
        }}
        Valores de 'action' para mídia: PLAY_QUERY, PLAY, PAUSE, NEXT, PREV. (Para buscas/pedidos, use sempre PLAY_QUERY com o campo 'query').
        O campo 'query_type' é obrigatório para PLAY_QUERY:
        - "entity": Bandas, artistas, álbuns específicos (ex: "Linkin Park", "Thriller").
        - "mood": Humores, atividades, intenções abstratas (ex: "música alegre", "para estudar").
        - "mixed": Uma mistura dos dois (ex: "rock animado", "lofi triste").

        4. Se for uma CHAMADA DE FERRAMENTA (pesquisa na web, status/diff git, inspeção de projeto):
        {{
            "type": "tool_call",
            "tool_name": "web_search", "git" ou "project_inspect",
            "parameters": {{
                "parametro": "valor"
            }},
            "explanation": "Uma frase explicando o que você vai consultar na ferramenta.",
            "risk_level": "safe"
        }}
        Use 'tool_call' sempre que o usuário pedir pesquisas na web, status/diff do git, ou inspeção de arquivos do projeto.

        Tiers de Risco:
        - "safe": Consultas, abrir pastas, git status, web search. (Default)
        - "low": Abrir apps, navegar em pastas.
        - "medium": Criar pastas/arquivos, rodar testes, git commit.
        - "high": Deletar arquivos específicos, alterar configurações.
        - "dangerous": Matar processos, deletar pastas.
        - "blocked": Formatar discos, deletar pastas do sistema, apagar disco C:.

        Regras:
        - SEMPRE retorne um "explanation" humano para ações e tool_calls.
        - Se a ação corresponder a um comando de plugin, use type "command" ou o
          tipo mais adequado dentro dos steps.
        - Retorne APENAS o JSON, sem markdown.
        """

        # Check Rate Limits
        if not rate_limiter.check_quotas():
            logger.info("Rate limit reached. Returning fallback message.")
            return {
                "type": "chat",
                "message": (
                    "Atingi o limite de uso de IA por hoje.\nPosso continuar com "
                    "comandos locais, ou você pode tentar novamente em algumas horas."
                ),
            }

        try:
            with self._lock:
                response = self._execute_with_fallback(prompt=prompt)
            result = response.content.strip()

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

                allowed_risks = [
                    "safe",
                    "low",
                    "medium",
                    "high",
                    "dangerous",
                    "blocked",
                ]
                if json_data.get("global_risk") not in allowed_risks:
                    logger.warning(
                        f"LLM response provided invalid/missing global_risk '{json_data.get('global_risk')}'. "
                        "Failing closed to 'high' risk."
                    )
                    json_data["global_risk"] = "high"

            logger.info(f"LLM Response Parsed: {json_data}")

            # Log usage
            total_tokens = response.usage.get("total_tokens", 0)
            rate_limiter.log_usage(token_count=total_tokens)

            # Sanitize output before saving or returning
            json_data = PromptGuard.sanitize_output(json_data)

            # 3. Save to cache
            if json_data.get("type") in ["action", "media"]:
                llm_cache.set(text, json_data)

            return json_data
        except LLMError as e:
            logger.error(f"LLM Provider Error: {e}")
            raise TechnicalError(f"LLM processing failed: {e}") from e
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            raise TechnicalError(f"LLM processing failed: {e}") from e

    def synthesize_tool_response(
        self, original_query: str, tool_name: str, tool_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Synthesizes a human-readable response or next action based on tool execution results."""
        prompt = f"""
        Você é o Jarvis, um assistente inteligente no Windows.
        O usuário pediu: "{original_query}"
        A ferramenta '{tool_name}' foi executada e retornou o seguinte resultado estruturado:
        {json.dumps(tool_result, ensure_ascii=False, indent=2)}

        Sua tarefa:
        1. Se os dados da ferramenta respondem à dúvida do usuário (ex: pesquisa web, git status, listagem de arquivos),
           retorne um JSON com type "chat":
           {{
               "type": "chat",
               "message": "Sua resposta clara, concisa e natural em Português para ser falada via TTS e exibida na tela."
           }}
        2. Se o usuário pediu para gerar um commit ou ação subsequente e a ferramenta retornou diff/dados suficientes:
           retorne um JSON com type "action", schema_version "1.0", intent "git_commit", global_risk "medium",
           explanation "Uma explicação da ação proposta.",
           e steps contendo:
           [
               {{
                   "type": "tool",
                   "step_risk": "medium",
                   "description": "Commitar alterações no Git",
                   "tool_name": "git",
                   "parameters": {{
                       "action": "commit",
                       "workspace": ".",
                       "message": "mensagem do commit seguindo Conventional Commits"
                   }}
               }}
           ]

        Retorne APENAS o JSON estrito, sem formatação markdown (```json).
        """
        try:
            with self._lock:
                response = self._execute_with_fallback(prompt=prompt)
            result = response.content.strip()
            if result.startswith("```json"):
                result = result[7:-3].strip()
            elif result.startswith("```"):
                result = result[3:-3].strip()

            json_data = json.loads(result)
            return PromptGuard.sanitize_output(json_data)
        except Exception as e:
            logger.error(f"Error synthesizing tool response: {e}")
            if tool_result.get("success"):
                output_val = (
                    tool_result.get("output")
                    or tool_result.get("tree")
                    or "Operação concluída com sucesso."
                )
                if isinstance(output_val, str) and len(output_val) > 300:
                    output_val = output_val[:300] + "..."
                return {
                    "type": "chat",
                    "message": f"Aqui está o resultado: {output_val}",
                }
            return {
                "type": "chat",
                "message": f"Houve um problema ao executar a ferramenta: {tool_result.get('error', 'desconhecido')}",
            }

    @time_it
    def generate_text(self, prompt: str) -> str:
        """Generates raw text from the LLM for a given prompt."""
        try:
            with self._lock:
                logger.info(
                    f"Sending prompt to LLM ({self.provider.provider}) for raw text generation..."
                )
                response = self.provider.generate_content(prompt=prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Error generating text from LLM: {e}")
            raise


llm_agent = LLMAgent()
