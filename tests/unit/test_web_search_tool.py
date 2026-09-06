import json
from unittest.mock import MagicMock, patch

from core.execution.execution_plan import RiskLevel
from core.tools.web_search_tool import WebSearchTool


def test_web_search_tool_metadata():
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "query" in schema["properties"]


@patch("urllib.request.urlopen")
def test_web_search_duckduckgo_instant_answer_success(mock_urlopen):
    # Mock DuckDuckGo JSON response
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "Heading": "Python Programming",
            "AbstractText": "Python is a high-level, general-purpose programming language.",
            "AbstractURL": "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "RelatedTopics": [
                {
                    "Text": "Python 3.13 released with performance improvements.",
                    "FirstURL": "https://python.org",
                }
            ],
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    tool = WebSearchTool()
    result = tool.execute(query="python programming", max_results=3)

    assert result["success"] is True
    assert len(result["results"]) >= 1
    assert "Python is a high-level" in result["results"][0]["snippet"]


@patch("urllib.request.urlopen")
def test_web_search_timeout_handling(mock_urlopen):
    mock_urlopen.side_effect = TimeoutError("Connection timed out")

    tool = WebSearchTool(timeout_seconds=1.0)
    result = tool.execute(query="python 3.13")

    assert result["success"] is False
    assert "timed out" in result["error"].lower()


@patch.dict("os.environ", {"TAVILY_API_KEY": "tvly-test-123"})
@patch("urllib.request.urlopen")
def test_web_search_tavily_when_key_present(mock_urlopen):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "results": [
                {
                    "title": "Latest Python Docs",
                    "content": "Official Python 3.13 documentation",
                    "url": "https://docs.python.org",
                }
            ]
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    tool = WebSearchTool(provider="tavily")
    result = tool.execute(query="python docs")

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Latest Python Docs"


def test_web_search_empty_query():
    tool = WebSearchTool()
    result = tool.execute(query="")
    assert result["success"] is False
    assert "empty" in result["error"].lower()
