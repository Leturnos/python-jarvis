import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.tools.base import BaseTool


class WeatherTool(BaseTool):
    """Fetches real-time weather forecasts via Open-Meteo public APIs."""

    name = "weather"
    description = (
        "Consulta a previsão do tempo e temperatura atual para uma cidade "
        "usando a API Open-Meteo. Se a cidade não for informada, usa a cidade padrão."
    )
    risk_level = RiskLevel.SAFE

    WMO_CODE_MAP = {
        0: "Céu limpo",
        1: "Predominantemente limpo",
        2: "Parcialmente nublado",
        3: "Encoberto",
        45: "Nevoeiro",
        48: "Nevoeiro com depósito de geada",
        51: "Garoa leve",
        53: "Garoa moderada",
        55: "Garoa densa",
        61: "Chuva fraca",
        63: "Chuva moderada",
        65: "Chuva forte",
        71: "Neve fraca",
        73: "Neve moderada",
        75: "Neve forte",
        80: "Pancadas de chuva leves",
        81: "Pancadas de chuva moderadas",
        82: "Pancadas de chuva violentas",
        95: "Tempestade com trovoadas",
        96: "Tempestade com granizo leve",
        99: "Tempestade com granizo forte",
    }

    BRAZILIAN_STATES = {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }

    def __init__(
        self,
        default_city: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._custom_default_city = default_city
        cfg = config.get("tools", {}).get("weather", {})
        self.default_city = (
            default_city
            if default_city is not None
            else cfg.get("default_city", "São Paulo")
        )
        self.timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else cfg.get("timeout_seconds", 5.0)
        )

    @property
    def configured_city(self) -> str:
        if self._custom_default_city:
            return self._custom_default_city
        cfg = config.get("tools", {}).get("weather", {})
        val = cfg.get("default_city")
        if val and str(val).strip():
            return str(val).strip()
        return self.default_city or "São Paulo"

    def _sanitize_city_name(self, city: str) -> str:
        clean = city.strip()
        # Remove country suffixes like ', Brasil', ', Brazil', '- BR'
        clean = re.sub(r"[\s,\-/]+(Brasil|Brazil|BR)\b", "", clean, flags=re.IGNORECASE)
        # Remove Brazilian state suffixes like '-MG', ' - MG', ', MG', '/MG'
        pattern = r"[\s,\-/]+(" + "|".join(self.BRAZILIAN_STATES) + r")\b"
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
        clean = clean.strip(" ,.-/")
        return clean or city.strip()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": (
                        "Nome da cidade a consultar (ex: 'São Paulo', 'Curitiba', 'Lisboa'). "
                        "Opcional; usa a cidade configurada se não informada."
                    ),
                }
            },
        }

    def execute(self, city: str | None = None, **kwargs: Any) -> dict[str, Any]:
        target_city = city.strip() if city and city.strip() else self.configured_city
        is_explicit_city = bool(city and city.strip())
        logger.info(f"WeatherTool: Querying weather for '{target_city}'")

        try:
            # 1. Geocoding
            coords = self._geocode(target_city)
            if (
                not coords
                and not is_explicit_city
                and target_city.lower() != "são paulo"
            ):
                logger.warning(
                    f"WeatherTool: Configured default city '{target_city}' not found. Falling back to 'São Paulo'."
                )
                coords = self._geocode("São Paulo")

            if not coords:
                return {
                    "success": False,
                    "error": f"Cidade '{target_city}' não encontrada.",
                }

            lat, lon, resolved_name = coords

            # 2. Weather Forecast
            weather_data = self._fetch_weather(lat, lon)
            current = weather_data.get("current", {})
            daily = weather_data.get("daily", {})

            w_code = current.get("weather_code", 0)
            condition = self.WMO_CODE_MAP.get(w_code, "Tempo instável")

            today_forecast = None
            max_temps = daily.get("temperature_2m_max", [])
            if max_temps:
                max_temp = max_temps[0]
                min_temps = daily.get("temperature_2m_min", [])
                min_temp = min_temps[0] if min_temps else None
                rain_prob_list = daily.get("precipitation_probability_max", [])
                rain_prob = rain_prob_list[0] if rain_prob_list else None
                rain_sum_list = daily.get("precipitation_sum", [])
                rain_sum = rain_sum_list[0] if rain_sum_list else 0.0
                daily_codes = daily.get("weather_code", [])
                daily_w_code = daily_codes[0] if daily_codes else w_code
                daily_condition = self.WMO_CODE_MAP.get(daily_w_code, condition)

                rain_expected = (
                    (rain_prob is not None and rain_prob >= 40)
                    or (rain_sum is not None and rain_sum > 0.5)
                    or (w_code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99])
                )

                today_forecast = {
                    "max_temperature": max_temp,
                    "min_temperature": min_temp,
                    "rain_probability_percent": rain_prob,
                    "rain_expected": bool(rain_expected),
                    "precipitation_sum_mm": rain_sum,
                    "condition_summary": daily_condition,
                }

            return {
                "success": True,
                "city": resolved_name,
                "temperature": current.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "condition": condition,
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "precipitation_mm": current.get("precipitation", 0.0),
                "today_forecast": today_forecast,
            }
        except TimeoutError:
            logger.warning(f"WeatherTool: Request timed out for '{target_city}'")
            return {
                "success": False,
                "error": f"Tempo limite excedido ao consultar o clima para '{target_city}'.",
            }
        except urllib.error.URLError as ue:
            logger.warning(f"WeatherTool: Network error for '{target_city}': {ue}")
            return {
                "success": False,
                "error": f"Falha de conexão ao consultar o clima para '{target_city}'.",
            }
        except Exception as e:
            logger.error(f"WeatherTool error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _query_geocoding(self, city: str) -> tuple[float, float, str] | None:
        encoded = urllib.parse.quote(city)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=pt&format=json"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-AI-Assistant/1.0"}
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results")
        if not results:
            return None

        first = results[0]
        name = first.get("name", city)
        admin1 = first.get("admin1", "")
        country = first.get("country", "")
        display = ", ".join(part for part in [name, admin1, country] if part)

        return float(first["latitude"]), float(first["longitude"]), display

    def _geocode(self, city: str) -> tuple[float, float, str] | None:
        candidate = self._sanitize_city_name(city)
        coords = self._query_geocoding(candidate)
        if coords:
            return coords

        if candidate != city.strip():
            coords = self._query_geocoding(city.strip())
            if coords:
                return coords

        return None

    def _fetch_weather(self, lat: float, lon: float) -> dict[str, Any]:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"
            "&timezone=auto"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-AI-Assistant/1.0"}
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
