from core.media.nlp import NLPProcessor

def test_nlp_scoring():
    processor = NLPProcessor("data/media/playlists.json")
    # Mock data directly for deterministic testing
    processor.keywords = {
        "happy_hits": ["alegre", "feliz", "animad"]
    }
    
    match, score = processor.score_query("quero ouvir uma musica muito feliz e animada")
    assert match == "happy_hits"
    assert score >= 0.8  # feliz (+0.4) and animada (+0.4)
    
    match_none, score_none = processor.score_query("nostalgico")
    assert match_none is None
    assert score_none == 0.0
