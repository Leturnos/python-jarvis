import sys
from unittest.mock import MagicMock, patch

for mod in ["winsound"]:
    sys.modules[mod] = MagicMock()

from core.audio.audio_cues import AudioCueManager, CueType  # noqa: E402


def test_play_cue_debounces_rapid_triggers():
    config = {"audio_cues": {"enabled": True, "debounce_ms": 200}}
    manager = AudioCueManager(config)

    with patch("core.audio.audio_cues._executor.submit") as mock_submit:
        # First call triggers sound
        assert manager.play_cue(CueType.WAKE) is True
        # Immediate second call within 200ms window gets debounced
        assert manager.play_cue(CueType.WAKE) is False
        mock_submit.assert_called_once()
