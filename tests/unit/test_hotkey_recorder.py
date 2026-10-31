from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from core.ui.tabs.settings_tab import SettingsTab
from core.ui.widgets.hotkey_recorder import (
    HotkeyRecorder,
    normalize_hotkey_parts,
)


def test_normalize_hotkey_parts():
    assert normalize_hotkey_parts(["left ctrl", "left alt"]) == "ctrl+alt"
    assert normalize_hotkey_parts(["p", "left shift", "left ctrl"]) == "ctrl+shift+p"
    assert normalize_hotkey_parts(["space", "left alt"]) == "alt+space"
    assert normalize_hotkey_parts(["f12"]) == "f12"
    assert normalize_hotkey_parts(["right ctrl", "right shift", "k"]) == "ctrl+shift+k"
    assert normalize_hotkey_parts(["alt gr"]) == "alt"


def test_hotkey_recorder_workflow():
    _ = QApplication.instance() or QApplication([])
    with patch("keyboard.hook") as mock_hook, patch("keyboard.unhook") as mock_unhook:
        mock_hook.return_value = 12345
        recorder = HotkeyRecorder(countdown_seconds=5)

        captured_records = []
        preview_records = []
        timeout_records = []
        cancelled_records = []

        recorder.hotkey_captured.connect(captured_records.append)
        recorder.live_preview.connect(preview_records.append)
        recorder.timeout.connect(lambda: timeout_records.append(True))
        recorder.cancelled.connect(lambda: cancelled_records.append(True))

        recorder.start()
        assert recorder.is_active
        assert mock_hook.called

        # Simulate Ctrl down, Alt down, Alt up, Ctrl up
        recorder._on_key_event("left ctrl", "down")
        assert "ctrl" in preview_records[-1]

        recorder._on_key_event("left alt", "down")
        assert "ctrl+alt" in preview_records[-1]

        recorder._on_key_event("left alt", "up")
        assert not captured_records  # Still holding Ctrl

        recorder._on_key_event("left ctrl", "up")
        assert captured_records == ["ctrl+alt"]
        assert not recorder.is_active
        assert mock_unhook.called


def test_hotkey_recorder_esc_cancels():
    _ = QApplication.instance() or QApplication([])
    with patch("keyboard.hook"), patch("keyboard.unhook"):
        recorder = HotkeyRecorder(countdown_seconds=5)
        cancelled = []
        recorder.cancelled.connect(lambda: cancelled.append(True))

        recorder.start()
        recorder._on_key_event("esc", "down")
        assert cancelled == [True]
        assert not recorder.is_active


def test_hotkey_recorder_timeout():
    _ = QApplication.instance() or QApplication([])
    with patch("keyboard.hook"), patch("keyboard.unhook"):
        recorder = HotkeyRecorder(countdown_seconds=2)
        timeouts = []
        recorder.timeout.connect(lambda: timeouts.append(True))

        recorder.start()
        recorder._on_timer_tick()  # 1s left
        assert not timeouts
        recorder._on_timer_tick()  # 0s left -> timeout
        assert timeouts == [True]
        assert not recorder.is_active


def test_settings_tab_record_buttons_integration():
    _ = QApplication.instance() or QApplication([])
    with patch("keyboard.hook"), patch("keyboard.unhook"):
        tab = SettingsTab()

        assert hasattr(tab, "ptt_record_btn")
        assert hasattr(tab, "cp_record_btn")
        assert tab.ptt_record_btn.text() == "⏺ Gravar"
        assert tab.cp_record_btn.text() == "⏺ Gravar"

        # Start PTT recording
        tab.ptt_record_btn.click()
        assert tab.ptt_record_btn.text() == "⏹ Cancelar"
        assert "Pressione as teclas" in tab.ptt_key_input.text()

        # Click again to cancel
        tab.ptt_record_btn.click()
        assert tab.ptt_record_btn.text() == "⏺ Gravar"

        # Start Command Palette recording
        tab.cp_record_btn.click()
        assert tab.cp_record_btn.text() == "⏹ Cancelar"
        assert "Pressione as teclas" in tab.command_palette_key_input.text()

        # Simulate hotkey capture
        assert tab._active_recorder is not None
        tab._active_recorder._on_key_event("left ctrl", "down")
        tab._active_recorder._on_key_event("k", "down")
        tab._active_recorder._on_key_event("k", "up")
        tab._active_recorder._on_key_event("left ctrl", "up")

        assert tab.command_palette_key_input.text() == "ctrl+k"
        assert tab.cp_record_btn.text() == "⏺ Gravar"
