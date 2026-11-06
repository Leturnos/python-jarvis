import os
import re
import urllib.parse
import urllib.request
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.logger_config import logger
from core.infra.network import get_ssl_context
from core.tools.base import BaseTool


class YouTubeTool(BaseTool):
    """Searches and plays YouTube videos directly in the default browser without requiring API keys."""

    name = "youtube"
    description = (
        "Pesquisa e reproduz vídeos especificamente no YouTube no navegador padrão. "
        "Use APENAS quando o usuário mencionar explicitamente 'YouTube' ou pedir um 'vídeo'. "
        "NÃO use para pedidos de Spotify ou música em geral."
    )
    risk_level = RiskLevel.SAFE

    def __init__(self, timeout_seconds: float = 6.0) -> None:
        self.timeout = timeout_seconds

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nome da música, artista, vídeo ou assunto a buscar no YouTube.",
                },
                "action": {
                    "type": "string",
                    "enum": ["play", "search"],
                    "description": "'play' (reproduzir o primeiro vídeo encontrado) ou 'search' (abrir a página de busca). Padrão: 'play'.",
                },
            },
            "required": ["query"],
        }

    def execute(
        self, query: str = "", action: str = "play", **kwargs: Any
    ) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {
                "success": False,
                "error": "O termo de busca do YouTube não pode estar vazio.",
            }

        act = (action or "play").strip().lower()

        if act == "search":
            return self._open_search_page(q)
        else:
            return self._play_first_video(q)

    def _open_search_page(self, query: str) -> dict[str, Any]:
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        try:
            os.startfile(search_url)
            logger.info(f"Opened YouTube search page: '{search_url}'")
            return {
                "success": True,
                "action": "search",
                "query": query,
                "url": search_url,
                "message": f"Abrindo busca no YouTube por '{query}'.",
            }
        except Exception as e:
            logger.error(f"Failed to open YouTube search URL: {e}")
            return {
                "success": False,
                "action": "search",
                "error": f"Falha ao abrir o navegador: {e}",
            }

    def _play_first_video(self, query: str) -> dict[str, Any]:
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        video_id = self._extract_first_video_id(search_url)

        target_url = (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else search_url
        )

        try:
            os.startfile(target_url)
            logger.info(f"Opened YouTube target (VideoID: {video_id}): '{target_url}'")
            msg = (
                f"Reproduzindo vídeo no YouTube para '{query}'."
                if video_id
                else f"Abrindo busca no YouTube para '{query}'."
            )
            return {
                "success": True,
                "action": "play",
                "query": query,
                "video_id": video_id,
                "url": target_url,
                "message": msg,
            }
        except Exception as e:
            logger.error(f"Failed to launch YouTube video URL: {e}")
            return {
                "success": False,
                "action": "play",
                "error": f"Falha ao abrir navegador: {e}",
            }

    def _extract_first_video_id(self, search_url: str) -> str | None:
        """Fetches the search results page and extracts the first video ID using regex."""
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        try:
            ctx = get_ssl_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Match YouTube video ID pattern in initial data JSON
            # Pattern matches: "videoId":"[11 chars]" or "videoId": "[11 chars]"
            match = re.search(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
            if match:
                vid = match.group(1)
                return vid
        except Exception as e:
            logger.warning(
                f"Could not extract direct YouTube video ID (falling back to search page): {e}"
            )
        return None
