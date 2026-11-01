import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.tools.base import BaseTool
from core.ui.notifications import JarvisNotifier


@dataclass
class ActiveTimer:
    timer_id: str
    label: str
    duration_seconds: float
    start_time: float
    end_time: float
    timer_thread: threading.Timer


class TimerTool(BaseTool):
    """Manages system timers, alarms, and Pomodoro focus intervals with Windows notifications and voice feedback."""

    name = "timer"
    description = (
        "Gerencia timers, alarmes e sessões de foco (Pomodoro). Permite criar timers em segundos ou minutos, "
        "listar timers ativos e cancelá-los, emitindo aviso sonoro e notificação ao finalizar."
    )
    risk_level = RiskLevel.SAFE

    def __init__(
        self,
        notifier: JarvisNotifier | None = None,
        tts_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.notifier = notifier or JarvisNotifier()
        self.tts_callback = tts_callback
        self._lock = threading.Lock()
        self._active_timers: dict[str, ActiveTimer] = {}

    def set_tts_callback(self, callback: Callable[[str], None] | None) -> None:
        """Sets or updates the voice callback invoked when a timer expires."""
        with self._lock:
            self.tts_callback = callback

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "pomodoro", "list", "cancel"],
                    "description": "Ação a executar: 'start' (novo timer), 'pomodoro' (foco de 25 min), 'list' (listar ativos) ou 'cancel' (cancelar).",
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "Duração do timer em segundos (opcional se minutes for informado).",
                },
                "minutes": {
                    "type": "number",
                    "description": "Duração do timer em minutos (ex: 5, 15, 25).",
                },
                "label": {
                    "type": "string",
                    "description": "Nome ou rótulo descritivo do timer (ex: 'Pomodoro', 'Bolo no forno', 'Reunião').",
                },
                "timer_id": {
                    "type": "string",
                    "description": "Identificador do timer para cancelamento específico (opcional).",
                },
                "cancel_all": {
                    "type": "boolean",
                    "description": "Se verdadeiro, cancela todos os timers ativos no momento.",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "list",
        duration_seconds: float | None = None,
        minutes: float | None = None,
        label: str = "",
        timer_id: str = "",
        cancel_all: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        act = (action or "list").strip().lower()

        if act == "start":
            return self._start_timer(
                duration_seconds=duration_seconds, minutes=minutes, label=label
            )
        elif act == "pomodoro":
            return self._start_pomodoro(minutes=minutes, label=label)
        elif act == "list":
            return self._list_timers()
        elif act == "cancel":
            return self._cancel_timer(
                timer_id=timer_id, label=label, cancel_all=cancel_all
            )
        else:
            return {
                "success": False,
                "error": f"Ação de timer desconhecida '{action}'. Use start, pomodoro, list ou cancel.",
            }

    def _start_timer(
        self,
        duration_seconds: float | None,
        minutes: float | None,
        label: str = "",
    ) -> dict[str, Any]:
        total_seconds = 0.0
        if duration_seconds is not None and duration_seconds > 0:
            total_seconds += float(duration_seconds)
        if minutes is not None and minutes > 0:
            total_seconds += float(minutes) * 60.0

        if total_seconds <= 0:
            return {
                "success": False,
                "error": "A duração do timer deve ser maior que zero (informe seconds ou minutes).",
            }

        timer_label = label.strip() or "Timer"
        tid = str(uuid.uuid4())[:8]
        now = time.time()
        end_time = now + total_seconds

        thread = threading.Timer(
            interval=total_seconds,
            function=self._on_timer_triggered,
            args=(tid, timer_label),
        )
        thread.daemon = True

        active = ActiveTimer(
            timer_id=tid,
            label=timer_label,
            duration_seconds=total_seconds,
            start_time=now,
            end_time=end_time,
            timer_thread=thread,
        )

        with self._lock:
            self._active_timers[tid] = active

        # Start thread outside lock to prevent contention
        thread.start()

        formatted_duration = self._format_seconds(total_seconds)
        logger.info(
            f"Started timer '{timer_label}' (ID: {tid}) for {formatted_duration}."
        )

        return {
            "success": True,
            "action": "start",
            "timer_id": tid,
            "label": timer_label,
            "duration_seconds": total_seconds,
            "formatted_duration": formatted_duration,
            "message": f"Timer de {formatted_duration} para '{timer_label}' iniciado com sucesso.",
        }

    def _start_pomodoro(self, minutes: float | None, label: str = "") -> dict[str, Any]:
        pomodoro_min = (
            minutes
            if (minutes is not None and minutes > 0)
            else float(
                config.get("tools", {}).get("timer", {}).get("pomodoro_minutes", 25)
            )
        )
        pomo_label = label.strip() or "Pomodoro (Foco)"
        return self._start_timer(
            duration_seconds=None, minutes=pomodoro_min, label=pomo_label
        )

    def _list_timers(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            timers_data = []
            for tid, t in list(self._active_timers.items()):
                rem = max(0.0, t.end_time - now)
                timers_data.append(
                    {
                        "timer_id": tid,
                        "label": t.label,
                        "duration_seconds": t.duration_seconds,
                        "remaining_seconds": round(rem, 1),
                        "formatted_remaining": self._format_seconds(rem),
                    }
                )

        return {
            "success": True,
            "action": "list",
            "count": len(timers_data),
            "timers": timers_data,
        }

    def _cancel_timer(
        self, timer_id: str = "", label: str = "", cancel_all: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            if cancel_all:
                count = len(self._active_timers)
                for t in self._active_timers.values():
                    t.timer_thread.cancel()
                self._active_timers.clear()
                return {
                    "success": True,
                    "action": "cancel",
                    "cancelled_count": count,
                    "message": f"Todos os {count} timers foram cancelados.",
                }

            tid = timer_id.strip()
            target_id = None
            if tid and tid in self._active_timers:
                target_id = tid
            elif label.strip():
                clean_lbl = label.strip().lower()
                for k, v in self._active_timers.items():
                    if clean_lbl in v.label.lower():
                        target_id = k
                        break

            if not target_id:
                return {
                    "success": False,
                    "action": "cancel",
                    "error": "Nenhum timer correspondente foi encontrado para cancelar.",
                }

            t = self._active_timers.pop(target_id)
            t.timer_thread.cancel()
            return {
                "success": True,
                "action": "cancel",
                "timer_id": target_id,
                "label": t.label,
                "message": f"Timer '{t.label}' cancelado com sucesso.",
            }

    def _on_timer_triggered(self, timer_id: str, label: str) -> None:
        """Callback invoked in background thread when the timer duration elapses."""
        with self._lock:
            self._active_timers.pop(timer_id, None)

        msg = f"Tempo esgotado para o timer: '{label}'!"
        logger.info(f"Timer triggered: {msg}")

        # 1. Native Windows toast notification
        try:
            self.notifier.notify(
                title="⏱️ Jarvis - Timer Concluído", message=msg, duration=5
            )
        except Exception as e:
            logger.warning(f"Failed to display timer toast notification: {e}")

        # 2. Spoken notification via TTS callback or fallback SAPI
        spoken_text = f"Atenção: o timer de {label} acabou de terminar."
        if self.tts_callback:
            try:
                self.tts_callback(spoken_text)
                return
            except Exception as e:
                logger.warning(f"TTS callback failed on timer trigger: {e}")

        # Fallback direct speech in isolated thread with proper COM initialization and teardown
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Speak(
                    spoken_text, 0
                )  # Synchronous speaking in this background thread
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug(f"Direct SAPI speech fallback error: {e}")

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        s = int(round(seconds))
        if s < 60:
            return f"{s}s"
        mins = s // 60
        rem_sec = s % 60
        if rem_sec == 0:
            return f"{mins}min"
        return f"{mins}min {rem_sec}s"
