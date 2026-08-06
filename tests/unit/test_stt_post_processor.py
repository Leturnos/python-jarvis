import sys
from unittest.mock import MagicMock

# Mock dependencies that attempt to load C-extension DLLs in sandbox environment
for mod in [
    "numpy",
    "faster_whisper",
    "win32com",
    "win32com.client",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
]:
    sys.modules[mod] = MagicMock()

from core.audio.stt_engine import STTEngine  # noqa: E402
from core.shared.utils import post_process_stt_text  # noqa: E402


def test_post_process_stt_text_uses_regex_word_boundaries():
    assert post_process_stt_text("abrir vies code agora") == "abrir VS Code agora"
    assert post_process_stt_text("tocar no espotifai") == "tocar no Spotify"
    assert post_process_stt_text("abrir warpe") == "abrir Warp"
    assert post_process_stt_text("warper") == "warper"


def test_build_initial_prompt_caps_at_150_chars():
    engine = STTEngine.__new__(STTEngine)
    keywords = [
        "VS Code",
        "Warp",
        "Spotify",
        "Terminal",
        "Docker",
        "Python",
        "VeryLongKeywordThatExceedsTheLimitExtremelyLongNames1234567890",
    ] * 10
    prompt = engine.build_initial_prompt(keywords, max_chars=150)
    assert len(prompt) <= 150
    assert "VS Code" in prompt
