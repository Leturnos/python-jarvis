import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.tools.base import BaseTool


class FinanceTool(BaseTool):
    """Queries live currency quotes and performs conversions via AwesomeAPI."""

    name = "finance"
    description = (
        "Consulta cotações de moedas em tempo real (dólar, euro, bitcoin, etc.) "
        "e realiza conversão monetária."
    )
    risk_level = RiskLevel.SAFE

    ALIAS_MAP = {
        "dolar": "USD-BRL",
        "dólar": "USD-BRL",
        "usd": "USD-BRL",
        "euro": "EUR-BRL",
        "eur": "EUR-BRL",
        "bitcoin": "BTC-BRL",
        "btc": "BTC-BRL",
        "libra": "GBP-BRL",
        "gbp": "GBP-BRL",
        "iene": "JPY-BRL",
        "jpy": "JPY-BRL",
    }

    def __init__(self, timeout_seconds: float | None = None) -> None:
        cfg = config.get("tools", {}).get("finance", {})
        self.timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else cfg.get("timeout_seconds", 5.0)
        )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "currencies": {
                    "type": "string",
                    "description": (
                        "Par de moedas ou apelido (ex: 'USD-BRL', 'EUR-BRL', 'dolar', 'euro', 'bitcoin')."
                    ),
                },
                "amount": {
                    "type": "number",
                    "description": "Quantidade para conversão monetária (opcional).",
                },
            },
            "required": ["currencies"],
        }

    def execute(
        self,
        currencies: str = "USD-BRL",
        amount: float | int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        clean_raw = (currencies or "USD-BRL").strip().lower().replace("/", "-")
        pair = self.ALIAS_MAP.get(clean_raw, clean_raw.upper())

        logger.info(f"FinanceTool: Fetching quote for '{pair}'")
        encoded_pair = urllib.parse.quote(pair)
        url = f"https://economia.awesomeapi.com.br/last/{encoded_pair}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-AI-Assistant/1.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            key = pair.replace("-", "")
            if key not in data:
                return {
                    "success": False,
                    "error": f"Cotação para a moeda '{pair}' não encontrada.",
                }

            quote = data[key]
            bid = float(quote.get("bid", 0.0))
            high = float(quote.get("high", 0.0))
            low = float(quote.get("low", 0.0))
            pct_raw = float(quote.get("pctChange", 0.0))
            pct_str = f"+{pct_raw:.2f}%" if pct_raw >= 0 else f"{pct_raw:.2f}%"

            result_payload: dict[str, Any] = {
                "success": True,
                "pair": pair,
                "name": quote.get("name", pair),
                "bid": bid,
                "high": high,
                "low": low,
                "pct_change": pct_str,
            }

            if amount is not None:
                try:
                    amt = float(amount)
                    result_payload["original_amount"] = amt
                    result_payload["converted_value"] = round(amt * bid, 2)
                except (ValueError, TypeError):
                    logger.warning(f"FinanceTool: Invalid amount value: {amount}")

            return result_payload
        except TimeoutError:
            logger.warning(f"FinanceTool: Request timed out for '{pair}'")
            return {
                "success": False,
                "error": f"Tempo limite excedido ao consultar cotação para '{pair}'.",
            }
        except urllib.error.HTTPError as he:
            if he.code == 404:
                logger.warning(
                    f"FinanceTool: Currency pair '{pair}' not found (HTTP 404)"
                )
                return {
                    "success": False,
                    "error": f"Cotação para a moeda '{pair}' não encontrada.",
                }
            logger.warning(f"FinanceTool: HTTP error {he.code} for '{pair}': {he}")
            return {
                "success": False,
                "error": f"Erro HTTP {he.code} ao consultar cotação.",
            }
        except urllib.error.URLError as ue:
            logger.warning(f"FinanceTool: Network error for '{pair}': {ue}")
            return {
                "success": False,
                "error": f"Falha de conexão ao consultar cotação para '{pair}'.",
            }
        except Exception as e:
            logger.error(f"FinanceTool error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
