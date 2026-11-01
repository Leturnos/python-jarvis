from typing import Any

import pyperclip

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.tools.base import BaseTool


class ClipboardTool(BaseTool):
    """Inspects or modifies the Windows system clipboard using pyperclip."""

    name = "clipboard"
    description = (
        "Lê ou escreve no clipboard (área de transferência) do Windows. "
        "Permite resumir, explicar erros ou traduzir o texto atualmente copiado pelo usuário, "
        "bem como copiar novos textos gerados para uso imediato."
    )
    risk_level = RiskLevel.SAFE

    def __init__(self, max_chars: int | None = None) -> None:
        cfg = config.get("tools", {}).get("clipboard", {})
        self.default_max_chars = (
            max_chars if max_chars is not None else int(cfg.get("max_chars", 4000))
        )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write"],
                    "description": "Ação no clipboard: 'read' para ler o texto copiado atual, ou 'write' para copiar novo texto.",
                },
                "content": {
                    "type": "string",
                    "description": "Texto a ser gravado no clipboard (obrigatório se action='write').",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Limite máximo de caracteres a ler para preservar o contexto do LLM (padrão: 4000).",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "read",
        content: str = "",
        max_chars: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        act = (action or "read").strip().lower()

        if act == "read":
            return self._read_clipboard(max_chars=max_chars)
        elif act in ("write", "copy"):
            return self._write_clipboard(content=content)
        else:
            return {
                "success": False,
                "error": f"Ação de clipboard desconhecida '{action}'. Use 'read' ou 'write'.",
            }

    def _read_clipboard(self, max_chars: int | None = None) -> dict[str, Any]:
        limit = max_chars if max_chars is not None else self.default_max_chars
        try:
            raw_text = pyperclip.paste()
        except Exception as e:
            logger.error(f"Failed to read from Windows clipboard: {e}")
            return {
                "success": False,
                "action": "read",
                "error": f"Falha ao ler área de transferência: {e}",
            }

        if not raw_text or not raw_text.strip():
            return {
                "success": True,
                "action": "read",
                "content": "",
                "length": 0,
                "truncated": False,
                "message": "A área de transferência está vazia ou não contém texto.",
            }

        total_len = len(raw_text)
        truncated = total_len > limit
        clean_content = raw_text[:limit]
        if truncated:
            clean_content += f"\n\n... [Texto truncado após {limit} caracteres de um total de {total_len}] ..."

        return {
            "success": True,
            "action": "read",
            "content": clean_content,
            "length": total_len,
            "truncated": truncated,
        }

    def _write_clipboard(self, content: str = "") -> dict[str, Any]:
        if content is None:
            content = ""

        try:
            pyperclip.copy(content)
            logger.info(f"Successfully copied {len(content)} characters to clipboard.")
            return {
                "success": True,
                "action": "write",
                "length": len(content),
                "message": f"{len(content)} caracteres copiados para a área de transferência.",
            }
        except Exception as e:
            logger.error(f"Failed to write to Windows clipboard: {e}")
            return {
                "success": False,
                "action": "write",
                "error": f"Falha ao copiar para a área de transferência: {e}",
            }
