from dataclasses import dataclass
from enum import Enum

from core.execution.execution_plan import ExecutionStep


class MediaAction(Enum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREV = "previous"
    PLAY_QUERY = "play_query"


class AutoplayStrategy(Enum):
    MEDIA_KEY = "media_key"
    TAB_ENTER = "tab_enter"
    NONE = "none"


class QueryType(Enum):
    MOOD = "mood"
    ENTITY = "entity"
    MIXED = "mixed"


@dataclass
class MediaIntent:
    action: MediaAction
    query: str | None = None
    query_type: QueryType | None = None
    provider_hint: str | None = None


@dataclass
class ResolvedMediaPlan:
    steps: list[ExecutionStep]
    strategy: AutoplayStrategy
    confidence: float = 1.0
    playlist_key: str | None = None


@dataclass
class LastMediaContext:
    provider: str
    resolved_strategy: str
    playlist_key: str | None = None
    raw_query: str | None = None


@dataclass
class MediaSessionState:
    active_provider: str | None = None
    last_context: LastMediaContext | None = None
