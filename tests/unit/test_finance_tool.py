import json
from unittest.mock import MagicMock, patch

from core.execution.execution_plan import RiskLevel
from core.tools.finance_tool import FinanceTool


def test_finance_tool_metadata() -> None:
    tool = FinanceTool()
    assert tool.name == "finance"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "currencies" in schema["properties"]
    assert "amount" in schema["properties"]


@patch("urllib.request.urlopen")
def test_finance_tool_usd_quote_success(mock_urlopen: MagicMock) -> None:
    api_response = MagicMock()
    api_response.read.return_value = json.dumps(
        {
            "USDBRL": {
                "code": "USD",
                "codein": "BRL",
                "name": "Dólar Americano/Real Brasileiro",
                "high": "5.7500",
                "low": "5.6800",
                "pctChange": "0.45",
                "bid": "5.7200",
            }
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = api_response

    tool = FinanceTool()
    result = tool.execute(currencies="dolar")

    assert result["success"] is True
    assert result["pair"] == "USD-BRL"
    assert result["bid"] == 5.72
    assert result["high"] == 5.75
    assert result["low"] == 5.68
    assert result["pct_change"] == "+0.45%"


@patch("urllib.request.urlopen")
def test_finance_tool_conversion_with_amount(mock_urlopen: MagicMock) -> None:
    api_response = MagicMock()
    api_response.read.return_value = json.dumps(
        {
            "EURBRL": {
                "code": "EUR",
                "codein": "BRL",
                "name": "Euro/Real Brasileiro",
                "high": "6.1500",
                "low": "6.0800",
                "pctChange": "-0.20",
                "bid": "6.1000",
            }
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = api_response

    tool = FinanceTool()
    result = tool.execute(currencies="EUR-BRL", amount=50.0)

    assert result["success"] is True
    assert result["bid"] == 6.10
    assert result["original_amount"] == 50.0
    assert result["converted_value"] == 305.0


@patch("urllib.request.urlopen")
def test_finance_tool_invalid_pair(mock_urlopen: MagicMock) -> None:
    api_response = MagicMock()
    api_response.read.return_value = json.dumps(
        {"status": 404, "message": "moeda nao encontrada"}
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = api_response

    tool = FinanceTool()
    result = tool.execute(currencies="INVALID-PAIR")

    assert result["success"] is False
    assert "não encontrada" in result["error"].lower()


@patch("urllib.request.urlopen")
def test_finance_tool_timeout(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = TimeoutError("Connection timed out")

    tool = FinanceTool(timeout_seconds=1.0)
    result = tool.execute(currencies="USD-BRL")

    assert result["success"] is False
    assert (
        "timed out" in result["error"].lower()
        or "tempo limite" in result["error"].lower()
    )


@patch("urllib.request.urlopen")
def test_finance_tool_http_404_error(mock_urlopen: MagicMock) -> None:
    import urllib.error

    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://economia.awesomeapi.com.br/last/XYZ", 404, "Not Found", {}, None
    )

    tool = FinanceTool()
    result = tool.execute(currencies="XYZ-BRL")

    assert result["success"] is False
    assert "não encontrada" in result["error"].lower()


@patch("urllib.request.urlopen")
def test_finance_tool_slash_normalization(mock_urlopen: MagicMock) -> None:
    api_response = MagicMock()
    api_response.read.return_value = json.dumps(
        {
            "USDBRL": {
                "name": "Dólar Americano/Real Brasileiro",
                "bid": "5.70",
                "high": "5.75",
                "low": "5.65",
                "pctChange": "0.10",
            }
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = api_response

    tool = FinanceTool()
    result = tool.execute(currencies="USD/BRL")

    assert result["success"] is True
    assert result["pair"] == "USD-BRL"
