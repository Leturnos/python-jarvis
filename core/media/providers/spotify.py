import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from core.execution.execution_plan import ExecutionStep, StepType
from core.media.models import (
    AutoplayStrategy,
    MediaAction,
    MediaIntent,
    QueryType,
    ResolvedMediaPlan,
)
from core.media.nlp import NLPProcessor
from core.shared.constants import Timing
from core.shared.paths import get_app_root

DEFAULT_PLAYLISTS_CATALOG: dict[str, Any] = {
    "intents": {
        "happy_hits": "spotify:playlist:37i9dQZF1DXdPec7aLTmlC",
        "focus": "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ",
        "workout": "spotify:playlist:37i9dQZF1DXe6bgV3TmZOL",
        "chill": "spotify:playlist:37i9dQZF1EVHGWrwldPRtj",
        "sad_songs": "spotify:playlist:2pnoYeER1oat11B3Vkpnm7",
        "party": "spotify:playlist:37i9dQZF1DXaXB8fQg7xif",
        "gaming": "spotify:playlist:37i9dQZF1DWTyiBJ6yEqeu",
        "fallback_playlist": "spotify:user:spotify:collection",
    },
    "keywords": {
        "happy_hits": [
            "alegre",
            "feliz",
            "animad",
            "pra cima",
            "bom humor",
            "radiante",
        ],
        "focus": [
            "focar",
            "concentrar",
            "estudar",
            "trabalhar",
            "foco",
            "produtividade",
            "ler",
        ],
        "workout": [
            "treinar",
            "malhar",
            "academia",
            "correr",
            "exercicio",
            "treino",
            "peso",
        ],
        "chill": [
            "relaxar",
            "calma",
            "dormir",
            "tranquil",
            "paz",
            "suave",
            "descansar",
        ],
        "sad_songs": ["triste", "bad", "melancolic", "chorar", "depre", "fossa"],
        "party": ["festa", "curtir", "comemorar", "dancar", "balada", "agito"],
        "gaming": [
            "jogar",
            "jogo",
            "jogos",
            "gamer",
            "game",
            "partida",
            "play",
            "lol",
            "cs",
            "valorant",
        ],
    },
}


class SpotifyProvider:
    def __init__(self, playlists_path: str | Path | None = None) -> None:
        if playlists_path is None:
            target_path = get_app_root() / "data" / "media" / "playlists.json"
            self._ensure_playlists_file(target_path)
            self.playlists_path = str(target_path)
        else:
            p = Path(playlists_path)
            resolved = p if p.is_absolute() else get_app_root() / p
            if playlists_path == "data/media/playlists.json":
                self._ensure_playlists_file(resolved)
            self.playlists_path = str(resolved)
        self.nlp = NLPProcessor(self.playlists_path)

    @staticmethod
    def _ensure_playlists_file(target_path: Path) -> None:
        """Creates data/media/playlists.json with default catalog if missing (e.g. after legacy updater /XD data)."""
        if target_path.exists():
            return
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PLAYLISTS_CATALOG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_intents(self) -> dict[str, Any]:
        try:
            with open(self.playlists_path, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f).get("intents", {}))
        except Exception:
            return dict(DEFAULT_PLAYLISTS_CATALOG["intents"])

    @staticmethod
    def _encode_search_uri(query: str) -> str:
        """Encodes non-ASCII characters in Spotify search query while preserving '+' for spaces."""
        parts = [quote(part, safe="") for part in query.split(" ")]
        return f"spotify:search:{'+'.join(parts)}"

    def resolve(self, intent: MediaIntent) -> ResolvedMediaPlan | None:
        if intent.action == MediaAction.PLAY_QUERY:
            intents_dict = self._load_intents()
            query = intent.query.lower() if intent.query else ""
            q_type = intent.query_type

            uri = None
            strategy = AutoplayStrategy.MEDIA_KEY
            confidence = 1.0
            playlist_key = None

            if q_type == QueryType.ENTITY:
                uri = self._encode_search_uri(query)
                strategy = AutoplayStrategy.TAB_ENTER
            else:
                # MOOD or MIXED
                match_key, score = self.nlp.score_query(query)
                if match_key and score >= 0.4:
                    uri = intents_dict.get(match_key)
                    confidence = score
                    playlist_key = match_key
                else:
                    uri = intents_dict.get("fallback_playlist")
                    confidence = 0.0
                    playlist_key = "fallback_playlist"

                strategy = AutoplayStrategy.MEDIA_KEY

            # Absolute fallback if json is broken
            if not uri:
                uri = self._encode_search_uri(query)
                strategy = AutoplayStrategy.TAB_ENTER

            steps = [
                ExecutionStep(
                    type=StepType.OPEN_APP,
                    payload={"target": uri},
                    description=f"Open Spotify: {query}",
                ),
                ExecutionStep(
                    type=StepType.WAIT,
                    payload={"duration": Timing.MEDIA_STARTUP_DELAY},
                    description="Wait for Spotify load",
                ),
            ]
            if strategy in (AutoplayStrategy.TAB_ENTER, AutoplayStrategy.MEDIA_KEY):
                steps.append(
                    ExecutionStep(
                        type=StepType.FOCUS_WINDOW,
                        payload={"target": "spotify"},
                        description="Focus Spotify",
                    )
                )

            return ResolvedMediaPlan(
                steps=steps,
                strategy=strategy,
                confidence=confidence,
                playlist_key=playlist_key,
            )
        return None
