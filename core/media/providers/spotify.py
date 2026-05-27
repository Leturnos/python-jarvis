import json
from typing import List
from core.media.models import MediaIntent, ResolvedMediaPlan, AutoplayStrategy, MediaAction
from core.execution.execution_plan import ExecutionStep, StepType

class SpotifyProvider:
    def __init__(self, playlists_path="data/media/playlists.json"):
        self.playlists_path = playlists_path

    def _load_playlists(self):
        try:
            with open(self.playlists_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def resolve(self, intent: MediaIntent) -> ResolvedMediaPlan:
        if intent.action == MediaAction.PLAY_QUERY:
            playlists = self._load_playlists()
            query = intent.query.lower() if intent.query else ""
            
            # 1. Check curated
            uri = playlists.get(query)
            strategy = AutoplayStrategy.MEDIA_KEY
            
            if not uri:
                # 2. Search fallback
                uri = f"spotify:search:{query.replace(' ', '+')}"
                strategy = AutoplayStrategy.TAB_ENTER
                
            steps = [
                ExecutionStep(type=StepType.OPEN_APP, payload={"target": uri}, description=f"Open Spotify: {query}"),
                ExecutionStep(type=StepType.WAIT, payload={"duration": 3.0}, description="Wait for Spotify load")
            ]
            return ResolvedMediaPlan(steps=steps, strategy=strategy)
        return None
