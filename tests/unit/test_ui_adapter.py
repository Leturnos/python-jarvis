import time
from unittest.mock import MagicMock

import numpy as np

from core.runtime.state import JarvisState, state_manager
from core.ui.adapter import JarvisTrayAdapter, JarvisUIAdapter


class TestJarvisUIAdapter:
    def test_init_string_and_list(self) -> None:
        a1 = JarvisUIAdapter("Hey Jarvis")
        assert a1.wakeword_name == "Hey Jarvis"

        a2 = JarvisUIAdapter(["Jarvis", "Computer"])
        assert a2.wakeword_name == "Jarvis, Computer"

    def test_update_and_signals(self) -> None:
        adapter = JarvisUIAdapter("Jarvis")
        emitted = []
        adapter.visual_state_updated.connect(lambda s: emitted.append(s))

        audio_samples = np.array([500, -500, 1000], dtype=np.int16)
        adapter.update(status="Ouvindo", score=0.95, volume=audio_samples, mode="ptt")

        assert len(emitted) == 1
        state = emitted[0]
        assert state["status"] == "Ouvindo"
        assert state["score"] == 0.95
        assert state["mode"] == "ptt"
        assert state["volume"] > 0

    def test_set_mode(self) -> None:
        adapter = JarvisUIAdapter("Jarvis")
        emitted = []
        adapter.visual_state_updated.connect(lambda s: emitted.append(s))

        adapter.set_mode("wakeword")
        assert len(emitted) == 1
        assert emitted[0]["mode"] == "wakeword"

    def test_backend_state_change_callback(self) -> None:
        adapter = JarvisUIAdapter("Jarvis")
        emitted = []
        adapter.visual_state_updated.connect(lambda s: emitted.append(s))

        adapter._on_backend_state_change(
            JarvisState.IDLE, JarvisState.LISTENING, context=None
        )
        assert len(emitted) == 1
        assert emitted[0]["state"] == JarvisState.LISTENING

    def test_dummy_live_context(self) -> None:
        adapter = JarvisUIAdapter("Jarvis")
        live = adapter.get_live()
        with live:
            pass
        live.stop()


class TestJarvisTrayAdapter:
    def test_set_mute_and_unmute(self) -> None:
        notifier = MagicMock()
        tray = JarvisTrayAdapter(notifier=notifier)

        # Mute for 10 minutes
        tray.set_mute(10)
        assert tray.mute_until > time.time()
        assert state_manager.get_state() == JarvisState.MUTED
        assert tray.is_muted() is True
        notifier.notify.assert_called_once()

        # Unmute
        tray.set_mute(0)
        assert tray.mute_until == 0.0
        assert state_manager.get_state() == JarvisState.IDLE
        assert tray.is_muted() is False

    def test_is_muted_expired(self) -> None:
        notifier = MagicMock()
        tray = JarvisTrayAdapter(notifier=notifier)

        tray.mute_until = time.time() - 10  # Expired in past
        state_manager.set_state(JarvisState.MUTED)

        assert tray.is_muted() is False
        assert state_manager.get_state() == JarvisState.IDLE
        assert tray.mute_until == 0.0
