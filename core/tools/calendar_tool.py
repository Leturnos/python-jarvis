import ipaddress
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.infra.network import get_ssl_context
from core.security.path_guard import PathGuard
from core.shared.errors import SecurityError
from core.tools.base import BaseTool


@dataclass
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime | None
    location: str | None
    description: str | None
    is_all_day: bool = False

    def to_dict(self) -> dict[str, Any]:
        if self.is_all_day:
            formatted_time = "Dia inteiro"
        else:
            formatted_time = self.start.strftime("%H:%M") + (
                f" até {self.end.strftime('%H:%M')}" if self.end else ""
            )

        return {
            "title": self.summary,
            "start": (
                self.start.strftime("%Y-%m-%d")
                if self.is_all_day
                else self.start.strftime("%Y-%m-%d %H:%M")
            ),
            "end": (
                self.end.strftime("%Y-%m-%d")
                if self.end and self.is_all_day
                else (self.end.strftime("%Y-%m-%d %H:%M") if self.end else None)
            ),
            "location": self.location,
            "description": self.description,
            "formatted_time": formatted_time,
            "is_all_day": self.is_all_day,
        }


class CalendarTool(BaseTool):
    """Parses standard iCalendar (.ics) feeds from Google Calendar, Outlook, or Apple Calendar without OAuth."""

    name = "calendar"
    description = (
        "Consulta compromissos e reuniões futuras da agenda do usuário via link ou arquivo "
        "iCalendar (.ics) privado sem necessidade de autenticação complexa."
    )
    risk_level = RiskLevel.SAFE

    def __init__(
        self,
        ics_url: str | None = None,
        timeout_seconds: float = 8.0,
        path_guard: PathGuard | None = None,
    ) -> None:
        self._ics_url_override = ics_url
        self.timeout = timeout_seconds
        self.path_guard = path_guard or PathGuard()

    @property
    def ics_url(self) -> str:
        if self._ics_url_override is not None:
            return self._ics_url_override
        configured = config.get("tools", {}).get("calendar", {}).get("ics_url", "")
        return str(configured).strip()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "upcoming", "week"],
                    "description": "Período a consultar: 'today' (hoje), 'tomorrow' (amanhã), 'upcoming' (próximos eventos) ou 'week' (semana).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Limite máximo de eventos a retornar (padrão: 5).",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "today",
        ics_url: str = "",
        limit: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        target_url = ics_url.strip() or self.ics_url
        if not target_url:
            return {
                "success": False,
                "action": action,
                "error": (
                    "Nenhum link ou arquivo de agenda (.ics) configurado. "
                    "Configure o link da agenda no painel de Configurações do Jarvis."
                ),
            }

        act = (action or "today").strip().lower()
        lim = max(1, min(limit, 20))

        try:
            raw_content = self._fetch_ics_content(target_url)
            events = self._parse_ics_events(raw_content)
        except Exception as e:
            logger.error(f"Error fetching or parsing calendar: {e}")
            return {
                "success": False,
                "action": act,
                "error": f"Falha ao carregar a agenda: {e}",
            }

        filtered = self._filter_events(events, act, lim)
        return {
            "success": True,
            "action": act,
            "count": len(filtered),
            "events": [e.to_dict() for e in filtered],
            "message": (
                f"{len(filtered)} compromisso(s) encontrado(s) para o período '{act}'."
                if filtered
                else f"Nenhum compromisso agendado para o período '{act}'."
            ),
        }

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False

        host = parsed.hostname or ""
        if not host:
            return False

        lower_host = host.lower()
        if lower_host in (
            "localhost",
            "127.0.0.1",
            "::1",
            "0.0.0.0",
            "169.254.169.254",
        ):
            return False

        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_private:
                return False
        except ValueError:
            # Valid domain name
            pass

        return True

    def _fetch_ics_content(self, source: str) -> str:
        clean_source = source.strip()

        if clean_source.startswith(("http://", "https://")):
            if not self._is_safe_url(clean_source):
                raise SecurityError(
                    f"URL de agenda não permitida ou insegura: {clean_source}"
                )

            req = urllib.request.Request(
                clean_source,
                headers={"User-Agent": "Jarvis-Calendar/1.0 (Windows NT 10.0)"},
            )
            ctx = get_ssl_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                content_bytes = resp.read()
                return str(content_bytes.decode("utf-8", errors="replace"))

        # Local file path validation via PathGuard
        validated_path = self.path_guard.validate_path(clean_source)
        if not validated_path.exists() or not validated_path.is_file():
            raise FileNotFoundError(
                f"Arquivo de agenda não encontrado: {validated_path}"
            )

        with open(validated_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def _parse_ics_events(self, ics_text: str) -> list[CalendarEvent]:
        # Unfold lines (RFC 5545: lines starting with space/tab continue previous line)
        lines = ics_text.splitlines()
        unfolded_lines: list[str] = []
        for line in lines:
            if line.startswith((" ", "\t")) and unfolded_lines:
                unfolded_lines[-1] += line[1:]
            else:
                unfolded_lines.append(line)

        events: list[CalendarEvent] = []
        in_event = False
        current_data: dict[str, str] = {}

        for line in unfolded_lines:
            stripped = line.strip()
            if stripped == "BEGIN:VEVENT":
                in_event = True
                current_data = {}
            elif stripped == "END:VEVENT" and in_event:
                in_event = False
                ev = self._build_event(current_data)
                if ev:
                    events.append(ev)
            elif in_event and ":" in stripped:
                key_part, _, val_part = stripped.partition(":")
                key_name = key_part.split(";")[0].upper()
                current_data[key_name] = val_part
                if "TZID=" in key_part:
                    m = re.search(r"TZID=([^;:]+)", key_part)
                    if m:
                        current_data[f"{key_name}_TZID"] = m.group(1).strip("\"'")

        # Sort events chronologically
        events.sort(key=lambda x: x.start)
        return events

    def _build_event(self, data: dict[str, str]) -> CalendarEvent | None:
        raw_start = data.get("DTSTART", "").strip()
        if not raw_start:
            return None

        is_all_day = len(raw_start) == 8 and raw_start.isdigit()

        summary = self._unescape_ics_text(data.get("SUMMARY", "Sem título"))
        location = self._unescape_ics_text(data.get("LOCATION", "")) or None
        description = self._unescape_ics_text(data.get("DESCRIPTION", "")) or None

        start_dt = self._parse_ics_datetime(raw_start, data.get("DTSTART_TZID"))
        if not start_dt:
            return None

        end_dt = None
        raw_end = data.get("DTEND", "").strip()
        if raw_end:
            end_dt = self._parse_ics_datetime(raw_end, data.get("DTEND_TZID"))

        return CalendarEvent(
            summary=summary,
            start=start_dt,
            end=end_dt,
            location=location,
            description=description,
            is_all_day=is_all_day,
        )

    def _parse_ics_datetime(
        self, value: str, tzid: str | None = None
    ) -> datetime | None:
        clean = value.strip()
        local_tz = datetime.now().astimezone().tzinfo

        # Format: YYYYMMDDTHHMMSSZ (UTC)
        if clean.endswith("Z"):
            try:
                dt_utc = datetime.strptime(clean, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=ZoneInfo("UTC")
                )
                return dt_utc.astimezone(local_tz)
            except Exception:
                pass

        # Format: YYYYMMDDTHHMMSS
        if "T" in clean:
            try:
                base_dt = datetime.strptime(clean[:15], "%Y%m%dT%H%M%S")
                if tzid:
                    try:
                        base_dt = base_dt.replace(tzinfo=ZoneInfo(tzid)).astimezone(
                            local_tz
                        )
                    except Exception:
                        base_dt = base_dt.replace(tzinfo=local_tz)
                else:
                    base_dt = base_dt.replace(tzinfo=local_tz)
                return base_dt
            except Exception:
                pass

        # Format: All-day date YYYYMMDD
        if len(clean) == 8 and clean.isdigit():
            try:
                d = datetime.strptime(clean, "%Y%m%d").date()
                return datetime.combine(d, datetime.min.time(), tzinfo=local_tz)
            except Exception:
                pass

        return None

    def _filter_events(
        self, events: list[CalendarEvent], period: str, limit: int
    ) -> list[CalendarEvent]:
        now = datetime.now().astimezone()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        result: list[CalendarEvent] = []

        for e in events:
            event_date = e.start.date()

            if period == "today":
                if event_date == today:
                    result.append(e)
            elif period == "tomorrow":
                if event_date == tomorrow:
                    result.append(e)
            elif period == "upcoming":
                if (e.end or e.start) >= now - timedelta(minutes=15):
                    result.append(e)
            elif period == "week":
                if today <= event_date <= (today + timedelta(days=7)):
                    result.append(e)
            else:
                # Default to today
                if event_date == today:
                    result.append(e)

            if len(result) >= limit:
                break

        return result

    @staticmethod
    def _unescape_ics_text(text: str) -> str:
        if not text:
            return ""
        return (
            text.replace(r"\n", "\n")
            .replace(r"\,", ",")
            .replace(r"\;", ";")
            .replace(r"\\", "\\")
            .strip()
        )
