from core.media.models import MediaAction, AutoplayStrategy, MediaIntent

def test_media_action_enum():
    assert MediaAction.PLAY.value == "play"
    assert MediaAction.PLAY_QUERY.value == "play_query"

def test_media_intent():
    intent = MediaIntent(action=MediaAction.PLAY_QUERY, query="alegre")
    assert intent.action == MediaAction.PLAY_QUERY
    assert intent.query == "alegre"
