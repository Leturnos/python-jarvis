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

@dataclass
class MediaIntent:
    action: MediaAction
    query: Optional[str] = None
    provider_hint: Optional[str] = None

@dataclass
class ResolvedMediaPlan:
    steps: List[ExecutionStep]
    strategy: AutoplayStrategy

@dataclass
class MediaSessionState:
    active_provider: Optional[str] = None
    current_query: Optional[str] = None
