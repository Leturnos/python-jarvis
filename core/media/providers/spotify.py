import json
from typing import List
from core.media.models import MediaIntent, ResolvedMediaPlan, AutoplayStrategy, MediaAction, QueryType
from core.execution.execution_plan import ExecutionStep, StepType
from core.media.nlp import NLPProcessor

class SpotifyProvider:
    def __init__(self, playlists_path="data/media/playlists.json"):
        self.playlists_path = playlists_path
        self.nlp = NLPProcessor(playlists_path)

    def _load_intents(self):
        try:
            with open(self.playlists_path, 'r', encoding='utf-8') as f:
                return json.load(f).get("intents", {})
        except:
            return {}

    def resolve(self, intent: MediaIntent) -> ResolvedMediaPlan:
        if intent.action == MediaAction.PLAY_QUERY:
            intents_dict = self._load_intents()
            query = intent.query.lower() if intent.query else ""
            q_type = intent.query_type
            
            uri = None
            strategy = AutoplayStrategy.MEDIA_KEY
            confidence = 1.0
            playlist_key = None

            if q_type == QueryType.ENTITY:
                uri = f"spotify:search:{query.replace(' ', '+')}"
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
            
            # Absolute fallback if json is broken
            if not uri:
                uri = f"spotify:search:{query.replace(' ', '+')}"
                strategy = AutoplayStrategy.TAB_ENTER

            steps = [
                ExecutionStep(type=StepType.OPEN_APP, payload={"target": uri}, description=f"Open Spotify: {query}"),
                ExecutionStep(type=StepType.WAIT, payload={"duration": 3.0}, description="Wait for Spotify load")
            ]
            return ResolvedMediaPlan(steps=steps, strategy=strategy, confidence=confidence, playlist_key=playlist_key)
        return None

