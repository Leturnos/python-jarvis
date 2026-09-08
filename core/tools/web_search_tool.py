import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """Lightweight HTTP search retriever querying DuckDuckGo or Tavily."""

    name = "web_search"
    description = (
        "Pesquisa na web por documentações, respostas técnicas e fatos em tempo real "
        "usando requisições HTTP leves sem inicializar navegadores."
    )
    risk_level = RiskLevel.SAFE

    def __init__(
        self,
        provider: str | None = None,
        timeout_seconds: float | None = None,
        max_results: int | None = None,
    ) -> None:
        cfg = config.get("tools", {}).get("web_search", {})
        self.provider = provider or cfg.get("provider", "duckduckgo")
        self.timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else cfg.get("timeout_seconds", 5.0)
        )
        self.default_max_results = (
            max_results if max_results is not None else cfg.get("max_results", 3)
        )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo de busca ou pergunta a ser pesquisada na web.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados resumidos a retornar (padrão: 3).",
                },
            },
            "required": ["query"],
        }

    def execute(
        self, query: str = "", max_results: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {"success": False, "error": "Search query cannot be empty."}

        limit = max_results if max_results is not None else self.default_max_results

        try:
            tavily_key = os.getenv("TAVILY_API_KEY")
            if self.provider == "tavily" and tavily_key:
                return self._search_tavily(q, limit, tavily_key)
            return self._search_duckduckgo(q, limit)
        except (TimeoutError, urllib.error.URLError) as e:
            logger.warning(f"WebSearchTool request error: {e}")
            if isinstance(e, TimeoutError) or "timed out" in str(e).lower():
                return {
                    "success": False,
                    "error": f"Search request timed out after {self.timeout}s.",
                }
            return {"success": False, "error": f"Network error during web search: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error in WebSearchTool: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _search_tavily(
        self, query: str, max_results: int, api_key: str
    ) -> dict[str, Any]:
        url = "https://api.tavily.com/search"
        payload = json.dumps({"query": query, "max_results": max_results}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_results = data.get("results", [])
        formatted = []
        for item in raw_results[:max_results]:
            snippet = item.get("content", "")[:500]
            formatted.append(
                {
                    "title": item.get("title", ""),
                    "snippet": snippet,
                    "url": item.get("url", ""),
                }
            )

        return {"success": True, "provider": "tavily", "results": formatted}

    def _search_duckduckgo(self, query: str, max_results: int) -> dict[str, Any]:
        # DuckDuckGo Instant Answer API
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Jarvis-Assistant/1.0 (Windows NT 10.0; Win64; x64)"
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw_text) if raw_text.strip() else {}
                data = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError, urllib.error.URLError):
            data = {}

        results: list[dict[str, Any]] = []
        heading = data.get("Heading", "")
        abstract = data.get("AbstractText", "")
        abstract_url = data.get("AbstractURL", "")

        if abstract:
            results.append(
                {
                    "title": heading or query,
                    "snippet": abstract[:500],
                    "url": abstract_url,
                }
            )

        # Add related topics if needed
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if isinstance(topic, dict) and "Text" in topic:
                results.append(
                    {
                        "title": topic.get("Text", "")[:60],
                        "snippet": topic.get("Text", "")[:500],
                        "url": topic.get("FirstURL", ""),
                    }
                )

        # If Instant Answer returned nothing, fallback to DuckDuckGo HTML Lite
        if not results:
            results = self._search_duckduckgo_html(query, max_results)

        return {"success": True, "provider": "duckduckgo", "results": results}

    def _search_duckduckgo_html(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            html_raw = resp.read().decode("utf-8", errors="replace")

        # Robust block-based parsing for DuckDuckGo HTML results
        blocks = re.findall(
            r'<div[^>]*class="[^"]*web-result[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*web-result[^"]*"|\Z)',
            html_raw,
            flags=re.DOTALL,
        )
        results: list[dict[str, Any]] = []
        for block in blocks:
            if len(results) >= max_results:
                break

            t_match = re.search(
                r'<a\b[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )
            s_match = re.search(
                r'<a\b[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )

            if not t_match and not s_match:
                continue

            raw_href = ""
            title = ""
            if t_match:
                tag_open = re.search(r"<a\b[^>]*>", block[t_match.start() :])
                if tag_open:
                    href_m = re.search(r'href="([^"]*)"', tag_open.group(0))
                    raw_href = href_m.group(1) if href_m else ""
                title = html.unescape(re.sub(r"<[^>]+>", "", t_match.group(1))).strip()

            snippet = (
                html.unescape(re.sub(r"<[^>]+>", "", s_match.group(1))).strip()
                if s_match
                else ""
            )

            # Extract destination URL from uddg query param if present
            url_str = ""
            if "uddg=" in raw_href:
                m_url = re.search(r"uddg=([^&]+)", raw_href)
                if m_url:
                    url_str = urllib.parse.unquote(m_url.group(1))
            elif raw_href.startswith("http"):
                url_str = raw_href

            if url_str.startswith("//"):
                url_str = f"https:{url_str}"

            results.append(
                {
                    "title": title or query,
                    "snippet": snippet[:500],
                    "url": url_str,
                }
            )

        return results
