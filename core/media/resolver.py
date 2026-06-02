from core.media.models import (
    AutoplayStrategy,
    MediaAction,
    MediaIntent,
    ResolvedMediaPlan,
)
from core.media.providers.os_controller import OSMediaController
from core.media.providers.spotify import SpotifyProvider


class MediaResolver:
    def __init__(self):
        self.spotify = SpotifyProvider()

    def resolve_intent(self, intent: MediaIntent) -> ResolvedMediaPlan:
        if intent.action == MediaAction.PLAY_QUERY:
            return self.spotify.resolve(intent)

        # Simple commands go directly to OS
        OSMediaController.send_command(intent.action)
        return ResolvedMediaPlan(steps=[], strategy=AutoplayStrategy.NONE)
