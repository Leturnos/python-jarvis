from enum import Enum
from dataclasses import dataclass
from typing import List, Optional
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
    query: Optional[str] = None
    query_type: Optional[QueryType] = None
    provider_hint: Optional[str] = None

@dataclass
class ResolvedMediaPlan:
    steps: List[ExecutionStep]
    strategy: AutoplayStrategy
    confidence: float = 1.0
    playlist_key: Optional[str] = None

@dataclass
class LastMediaContext:
    provider: str
    resolved_strategy: str
    playlist_key: Optional[str] = None
    raw_query: Optional[str] = None

@dataclass
class MediaSessionState:
    active_provider: Optional[str] = None
    last_context: Optional[LastMediaContext] = None
