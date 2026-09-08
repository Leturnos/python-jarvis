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


@patch("urllib.request.urlopen")
def test_web_search_duckduckgo_html_fallback(mock_urlopen):
    # Call 1: Instant Answer API returns empty JSON
    resp_api = MagicMock()
    resp_api.read.return_value = b"{}"

    # Call 2: HTML fallback returns web-result blocks
    html_mock = """
    <div class="result results_links results_links_deep web-result ">
        <h2 class="result__title">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&amp;rut=123">Welcome to Python.org</a>
        </h2>
        <a class="result__snippet" href="#">Python is an easy to learn programming language.</a>
    </div>
    """
    resp_html = MagicMock()
    resp_html.read.return_value = html_mock.encode("utf-8")

    mock_urlopen.return_value.__enter__.side_effect = [resp_api, resp_html]

    tool = WebSearchTool()
    result = tool.execute(query="como instalar python", max_results=1)

    assert result["success"] is True
    assert result["provider"] == "duckduckgo"
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Welcome to Python.org"
    assert result["results"][0]["url"] == "https://www.python.org/"
    assert "easy to learn" in result["results"][0]["snippet"]


@patch("urllib.request.urlopen")
def test_web_search_duckduckgo_malformed_json_fallback(mock_urlopen):
    # Call 1: Instant Answer API returns empty body / non-JSON
    resp_api = MagicMock()
    resp_api.read.return_value = b""

    # Call 2: HTML fallback returns result
    html_mock = """
    <div class="web-result">
        <a class="result__a" href="https://example.com/guide">Example Guide</a>
        <a class="result__snippet">Tutorial content</a>
    </div>
    """
    resp_html = MagicMock()
    resp_html.read.return_value = html_mock.encode("utf-8")

    mock_urlopen.return_value.__enter__.side_effect = [resp_api, resp_html]

    tool = WebSearchTool()
    result = tool.execute(query="search something", max_results=1)

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Example Guide"
    assert result["results"][0]["url"] == "https://example.com/guide"


@patch("urllib.request.urlopen")
def test_web_search_duckduckgo_html_unescape_and_attribute_order(mock_urlopen):
    # Call 1: Instant Answer API returns empty JSON
    resp_api = MagicMock()
    resp_api.read.return_value = b"{}"

    # Call 2: HTML with reversed attributes (href before class), entities (&amp;, &#x27;), and protocol-relative URL
    html_mock = """
    <div class="web-result">
        <h2>
            <a href="//duckduckgo.com/l/?uddg=%2F%2Fpython.org%2Fnews&amp;rut=1" class="result__a">What&#x27;s New in Python &amp; Friends</a>
        </h2>
        <a class="result__snippet">Updates &amp; improvements in 3.13.</a>
    </div>
    """
    resp_html = MagicMock()
    resp_html.read.return_value = html_mock.encode("utf-8")

    mock_urlopen.return_value.__enter__.side_effect = [resp_api, resp_html]

    tool = WebSearchTool()
    result = tool.execute(query="python news", max_results=1)

    assert result["success"] is True
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["title"] == "What's New in Python & Friends"
    assert res["snippet"] == "Updates & improvements in 3.13."
    assert res["url"] == "https://python.org/news"


@patch("urllib.request.urlopen")
def test_web_search_duckduckgo_non_dict_json_and_urlerror_fallback(mock_urlopen):
    import urllib.error

    # Call 1: Instant Answer API raises URLError (e.g. 503 or transient outage)
    # Call 2: HTML fallback succeeds
    html_mock = """
    <div class="web-result">
        <a class="result__a" href="https://fallback.org">Fallback Site</a>
        <a class="result__snippet">Content</a>
    </div>
    """
    resp_html = MagicMock()
    resp_html.read.return_value = html_mock.encode("utf-8")

    mock_urlopen.return_value.__enter__.side_effect = [
        urllib.error.URLError("Temporary outage"),
        resp_html,
    ]

    tool = WebSearchTool()
    result = tool.execute(query="fallback test", max_results=1)

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Fallback Site"
