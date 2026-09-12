import json
from unittest.mock import MagicMock, patch

from core.execution.execution_plan import RiskLevel
from core.tools.weather_tool import WeatherTool


def test_weather_tool_metadata() -> None:
    tool = WeatherTool()
    assert tool.name == "weather"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "city" in schema["properties"]


@patch("urllib.request.urlopen")
def test_weather_tool_success_with_city(mock_urlopen: MagicMock) -> None:
    geo_response = MagicMock()
    geo_response.read.return_value = json.dumps(
        {
            "results": [
                {
                    "name": "São Paulo",
                    "admin1": "São Paulo",
                    "country": "Brasil",
                    "latitude": -23.55,
                    "longitude": -46.63,
                }
            ]
        }
    ).encode("utf-8")

    forecast_response = MagicMock()
    forecast_response.read.return_value = json.dumps(
        {
            "current": {
                "temperature_2m": 24.5,
                "relative_humidity_2m": 65,
                "apparent_temperature": 25.1,
                "precipitation": 0.0,
                "weather_code": 1,
                "wind_speed_10m": 12.0,
            }
        }
    ).encode("utf-8")

    mock_urlopen.side_effect = [
        MagicMock(__enter__=MagicMock(return_value=geo_response)),
        MagicMock(__enter__=MagicMock(return_value=forecast_response)),
    ]

    tool = WeatherTool(default_city="Rio de Janeiro")
    result = tool.execute(city="São Paulo")

    assert result["success"] is True
    assert "São Paulo" in result["city"]
    assert result["temperature"] == 24.5
    assert result["apparent_temperature"] == 25.1
    assert result["humidity"] == 65
    assert "limpo" in result["condition"].lower()


@patch("urllib.request.urlopen")
def test_weather_tool_default_city_fallback(mock_urlopen: MagicMock) -> None:
    geo_response = MagicMock()
    geo_response.read.return_value = json.dumps(
        {
            "results": [
                {
                    "name": "Curitiba",
                    "admin1": "Paraná",
                    "country": "Brasil",
                    "latitude": -25.43,
                    "longitude": -49.27,
                }
            ]
        }
    ).encode("utf-8")

    forecast_response = MagicMock()
    forecast_response.read.return_value = json.dumps(
        {
            "current": {
                "temperature_2m": 18.0,
                "relative_humidity_2m": 80,
                "apparent_temperature": 18.0,
                "precipitation": 0.0,
                "weather_code": 0,
                "wind_speed_10m": 8.0,
            }
        }
    ).encode("utf-8")

    mock_urlopen.side_effect = [
        MagicMock(__enter__=MagicMock(return_value=geo_response)),
        MagicMock(__enter__=MagicMock(return_value=forecast_response)),
    ]

    tool = WeatherTool(default_city="Curitiba")
    result = tool.execute(city="")

    assert result["success"] is True
    assert "Curitiba" in result["city"]
    assert result["temperature"] == 18.0


@patch("urllib.request.urlopen")
def test_weather_tool_city_not_found(mock_urlopen: MagicMock) -> None:
    geo_response = MagicMock()
    geo_response.read.return_value = json.dumps({}).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = geo_response

    tool = WeatherTool()
    result = tool.execute(city="CidadeInexistenteXYZ123")

    assert result["success"] is False
    assert "não encontrada" in result["error"].lower()


@patch("urllib.request.urlopen")
def test_weather_tool_timeout(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = TimeoutError("Connection timed out")

    tool = WeatherTool(timeout_seconds=1.0)
    result = tool.execute(city="São Paulo")

    assert result["success"] is False
    assert (
        "timed out" in result["error"].lower()
        or "tempo limite" in result["error"].lower()
    )


@patch("urllib.request.urlopen")
def test_weather_tool_with_daily_forecast_and_rain(mock_urlopen: MagicMock) -> None:
    geo_response = MagicMock()
    geo_response.read.return_value = json.dumps(
        {
            "results": [
                {
                    "name": "São Paulo",
                    "admin1": "São Paulo",
                    "country": "Brasil",
                    "latitude": -23.55,
                    "longitude": -46.63,
                }
            ]
        }
    ).encode("utf-8")

    forecast_response = MagicMock()
    forecast_response.read.return_value = json.dumps(
        {
            "current": {
                "temperature_2m": 21.0,
                "relative_humidity_2m": 78,
                "apparent_temperature": 21.5,
                "precipitation": 0.0,
                "weather_code": 3,
                "wind_speed_10m": 10.0,
            },
            "daily": {
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [15.0],
                "precipitation_probability_max": [80],
                "precipitation_sum": [4.2],
                "weather_code": [61],
            },
        }
    ).encode("utf-8")

    mock_urlopen.side_effect = [
        MagicMock(__enter__=MagicMock(return_value=geo_response)),
        MagicMock(__enter__=MagicMock(return_value=forecast_response)),
    ]

    tool = WeatherTool()
    result = tool.execute(city="São Paulo")

    assert result["success"] is True
    assert "São Paulo" in result["city"]
    assert result["condition"] == "Encoberto"
    assert result["today_forecast"] is not None
    forecast = result["today_forecast"]
    assert forecast["max_temperature"] == 25.0
    assert forecast["min_temperature"] == 15.0
    assert forecast["rain_probability_percent"] == 80
    assert forecast["rain_expected"] is True
    assert forecast["precipitation_sum_mm"] == 4.2
    assert "chuva" in forecast["condition_summary"].lower()
