from core.media.models import LastMediaContext, MediaAction, MediaIntent, QueryType


def test_media_action_enum():
    assert MediaAction.PLAY.value == "play"
    assert MediaAction.PLAY_QUERY.value == "play_query"


def test_media_intent():
    intent = MediaIntent(action=MediaAction.PLAY_QUERY, query="alegre")
    assert intent.action == MediaAction.PLAY_QUERY
    assert intent.query == "alegre"


def test_query_type_enum():
    assert QueryType.MOOD.value == "mood"
    assert QueryType.ENTITY.value == "entity"
    assert QueryType.MIXED.value == "mixed"


def test_last_media_context():
    ctx = LastMediaContext(
        provider="spotify",
        resolved_strategy="curated",
        playlist_key="happy_hits",
        raw_query="toca algo feliz",
    )
    assert ctx.provider == "spotify"
    assert ctx.playlist_key == "happy_hits"
