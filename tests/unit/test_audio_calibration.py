from unittest.mock import MagicMock, patch

import pytest

from core.audio.audio_engine import get_audio_stream, get_input_devices
from core.audio.audio_loop import AudioLoopManager
from core.infra.config import update_yaml_device_index, update_yaml_float_setting
from core.runtime.state import JarvisState, StateManager
from core.ui.adapter import JarvisUIAdapter
from core.ui.widgets.audio_calibration_dialog import AudioCalibrationDialog


class TestAudioCalibrationCalculations:
    """Tests the heuristic calculation of threshold and gain recommendations."""

    def test_empty_samples_returns_defaults(self) -> None:
        recs = AudioCalibrationDialog.calculate_recommendations([])
        assert recs["threshold"] == 0.50
        assert recs["volume_multiplier"] == 1.0
        assert recs["speech_rms"] == 20.0

    def test_healthy_voice_samples_calculates_balanced_settings(self) -> None:
        samples = [
            {"score": 0.82, "rms": 45.0},
            {"score": 0.78, "rms": 40.0},
            {"score": 0.85, "rms": 48.0},
        ]
        recs = AudioCalibrationDialog.calculate_recommendations(samples)
        # min_score = 0.78 -> 0.78 * 0.82 = 0.6396 -> 0.64
        assert 0.60 <= recs["threshold"] <= 0.65
        assert recs["volume_multiplier"] == 1.0  # Normal healthy volume
        assert 15.0 <= recs["speech_rms"] <= 25.0

    def test_quiet_microphone_recommends_gain_boost(self) -> None:
        samples = [
            {"score": 0.50, "rms": 14.0},
            {"score": 0.45, "rms": 16.0},
            {"score": 0.48, "rms": 15.0},
        ]
        recs = AudioCalibrationDialog.calculate_recommendations(samples)
        assert recs["volume_multiplier"] == 1.4  # Boosted gain for low RMS
        assert 0.35 <= recs["threshold"] <= 0.42

    def test_threshold_respects_safety_bounds(self) -> None:
        # Very low scores should not drop below safety floor of 0.25
        low_samples = [{"score": 0.10, "rms": 20.0}]
        low_recs = AudioCalibrationDialog.calculate_recommendations(low_samples)
        assert low_recs["threshold"] == 0.25

        # Very high scores should not exceed safety ceiling of 0.80
        high_samples = [{"score": 0.99, "rms": 50.0}]
        high_recs = AudioCalibrationDialog.calculate_recommendations(high_samples)
        assert high_recs["threshold"] == 0.80

    def test_real_16bit_pcm_speech_rms_does_not_penalize_gain(self) -> None:
        samples = [
            {"score": 0.43, "rms": 1094.2},
            {"score": 0.35, "rms": 2140.1},
            {"score": 0.35, "rms": 2001.7},
        ]
        recs = AudioCalibrationDialog.calculate_recommendations(samples)
        assert recs["volume_multiplier"] == 1.0
        assert recs["threshold"] == 0.29

    def test_record_sample_caps_at_total_steps_and_auto_advances_on_16bit_pcm(
        self,
    ) -> None:
        from PySide6.QtWidgets import QApplication

        _ = QApplication.instance() or QApplication([])
        dlg = AudioCalibrationDialog()
        dlg._start_step(1)
        dlg._step_cooldown_until = 0.0

        # Simulate speaking on a 16-bit PCM mic (peak RMS ~2000, ambient silence RMS ~40)
        dlg._on_audio_data(score=0.45, rms=2000.0)
        assert dlg._is_utterance_active is True

        # Utterance ends (score drops to 0.02, RMS drops to ambient 45.0 < 2000 * 0.35)
        with patch("core.ui.widgets.audio_calibration_dialog.QTimer.singleShot"):
            dlg._on_audio_data(score=0.02, rms=45.0)
            assert len(dlg.samples) == 1

            # Record remaining samples and verify 4th sample is ignored
            dlg._record_sample(0.40, 1800.0)
            dlg._record_sample(0.38, 1900.0)
            dlg._record_sample(0.38, 1900.0)  # Extra call during 800ms timer window
            assert len(dlg.samples) == AudioCalibrationDialog.TOTAL_STEPS


class TestAudioInputDeviceDiscovery:
    """Tests enumeration of PyAudio input devices."""

    @patch("core.audio.audio_engine.pyaudio.PyAudio")
    def test_get_input_devices_filters_microphones(
        self, mock_pyaudio_cls: MagicMock
    ) -> None:
        mock_pa = MagicMock()
        mock_pyaudio_cls.return_value = mock_pa
        mock_pa.get_device_count.return_value = 3
        mock_pa.get_device_info_by_index.side_effect = [
            {"name": "Speakers", "maxInputChannels": 0},
            {"name": "USB Microphone", "maxInputChannels": 2},
            {"name": "Headset Mic", "maxInputChannels": 1},
        ]

        devs = get_input_devices()
        assert len(devs) == 2
        assert devs[0] == (1, "USB Microphone")
        assert devs[1] == (2, "Headset Mic")
        mock_pa.terminate.assert_called_once()

    @patch("core.audio.audio_engine.pyaudio.PyAudio")
    def test_get_input_devices_filters_virtual_and_duplicates(
        self, mock_pyaudio_cls: MagicMock
    ) -> None:
        mock_pa = MagicMock()
        mock_pyaudio_cls.return_value = mock_pa
        mock_pa.get_device_count.return_value = 6
        mock_pa.get_device_info_by_index.side_effect = [
            {"name": "Mapeador de som da Microsoft - Input", "maxInputChannels": 2},
            {"name": "Microfone (Realtek(R) Audio)", "maxInputChannels": 2},
            {"name": "Driver de captura de som primÃ¡rio", "maxInputChannels": 2},
            {"name": "Mixagem estÃ©reo (Realtek)", "maxInputChannels": 2},
            {"name": "Microfone (Realtek(R) Audio)", "maxInputChannels": 2},
            {"name": "Microphone (Camo)", "maxInputChannels": 2},
        ]

        devs = get_input_devices()
        assert len(devs) == 2
        assert devs[0] == (1, "Microfone (Realtek(R) Audio)")
        assert devs[1] == (5, "Microphone (Camo)")

    @patch("core.audio.audio_engine.pyaudio.PyAudio")
    def test_get_audio_stream_falls_back_to_default_on_device_failure(
        self, mock_pyaudio_cls: MagicMock
    ) -> None:
        mock_pa = MagicMock()
        mock_pyaudio_cls.return_value = mock_pa
        mock_stream = MagicMock()
        mock_pa.open.side_effect = [OSError("Invalid device index"), mock_stream]

        mock_config = {
            "voice_activation": {"device_index": 5, "frames_per_buffer": 1280}
        }
        pa, stream = get_audio_stream(config=mock_config)
        assert pa == mock_pa
        assert stream == mock_stream
        assert mock_pa.open.call_count == 2
        first_call_kwargs = mock_pa.open.call_args_list[0][1]
        second_call_kwargs = mock_pa.open.call_args_list[1][1]
        assert first_call_kwargs["input_device_index"] == 5
        assert "input_device_index" not in second_call_kwargs


class TestStateCalibrationTransitions:
    """Tests the StateManager handling of JarvisState.CALIBRATING."""

    def test_calibrating_transitions_lifecycle(self) -> None:
        sm = StateManager()
        assert sm.get_state() == JarvisState.IDLE

        # IDLE -> CALIBRATING
        sm.set_state(JarvisState.CALIBRATING)
        assert sm.get_state() == JarvisState.CALIBRATING

        # CALIBRATING -> IDLE
        sm.set_state(JarvisState.IDLE)
        assert sm.get_state() == JarvisState.IDLE

    def test_invalid_transition_logs_warning_and_preserves_safety(self) -> None:
        sm = StateManager()
        sm.set_state(JarvisState.EXECUTING)
        assert sm.get_state() == JarvisState.EXECUTING

        # EXECUTING -> CALIBRATING is not an allowed direct transition
        with patch("core.runtime.state.logger.warning") as mock_warn:
            sm.set_state(JarvisState.CALIBRATING)
            mock_warn.assert_called_once()

    def test_muted_and_suspended_can_enter_calibrating(self) -> None:
        sm = StateManager()

        # IDLE -> MUTED -> CALIBRATING -> IDLE
        sm.set_state(JarvisState.MUTED)
        assert sm.get_state() == JarvisState.MUTED
        with patch("core.runtime.state.logger.warning") as mock_warn:
            sm.set_state(JarvisState.CALIBRATING)
            mock_warn.assert_not_called()
        assert sm.get_state() == JarvisState.CALIBRATING
        sm.set_state(JarvisState.IDLE)
        assert sm.get_state() == JarvisState.IDLE

        # IDLE -> SUSPENDED -> CALIBRATING -> IDLE
        sm.set_state(JarvisState.SUSPENDED)
        assert sm.get_state() == JarvisState.SUSPENDED
        with patch("core.runtime.state.logger.warning") as mock_warn:
            sm.set_state(JarvisState.CALIBRATING)
            mock_warn.assert_not_called()
        assert sm.get_state() == JarvisState.CALIBRATING
        sm.set_state(JarvisState.IDLE)
        assert sm.get_state() == JarvisState.IDLE


class TestAudioLoopVolumeMultiplier:
    """Tests dynamic volume multiplier on AudioLoopManager."""

    def test_set_volume_multiplier_with_floor(self) -> None:
        mock_config = {
            "voice_activation": {"volume_multiplier": 1.2, "frames_per_buffer": 1280}
        }
        manager = AudioLoopManager(
            config=mock_config,
            dispatcher=MagicMock(),
            ui=MagicMock(),
            pa=MagicMock(),
            stream=MagicMock(),
        )
        assert manager.volume_multiplier == 1.2

        manager.set_volume_multiplier(1.8)
        assert manager.volume_multiplier == 1.8

        manager.set_volume_multiplier(-0.5)
        assert manager.volume_multiplier == 0.1  # Clamped to floor


class TestUIAdapterCalibrationDelegation:
    """Tests calibration signal emission and controller delegation."""

    def test_update_calibration_emits_qt_signal(self) -> None:
        adapter = JarvisUIAdapter("hey_jarvis")
        received: list[tuple[float, float]] = []
        adapter.calibration_data_updated.connect(lambda s, r: received.append((s, r)))

        adapter.update_calibration(0.85, 42.0)
        assert len(received) == 1
        assert received[0] == (0.85, 42.0)

    def test_apply_calibration_delegates_to_controller(self) -> None:
        adapter = JarvisUIAdapter("hey_jarvis")
        mock_controller = MagicMock()
        adapter.set_controller(mock_controller)

        adapter.apply_calibration(0.65, 1.3, 18.0)
        mock_controller.apply_audio_calibration.assert_called_once_with(0.65, 1.3, 18.0)


class TestConfigYamlAudioUpdaters:
    """Tests surgical YAML updates for float settings and device_index."""

    def test_update_yaml_device_index(self, tmp_path: pytest.TempPathFactory) -> None:
        dummy_yaml = tmp_path / "config.yaml"  # type: ignore[operator]
        dummy_yaml.write_text(
            "voice_activation:\n  device_index: null  # Default\n  volume_multiplier: 1.0\n",
            encoding="utf-8",
        )

        with patch("core.infra.config.get_user_config_path", return_value=dummy_yaml):
            update_yaml_device_index(3)
            content = dummy_yaml.read_text(encoding="utf-8")
            assert "device_index: 3" in content

            update_yaml_device_index(None)
            content = dummy_yaml.read_text(encoding="utf-8")
            assert "device_index: null" in content

    def test_update_yaml_float_setting(self, tmp_path: pytest.TempPathFactory) -> None:
        dummy_yaml = tmp_path / "config.yaml"  # type: ignore[operator]
        dummy_yaml.write_text(
            "voice_activation:\n  wake_word:\n    threshold: 0.50  # Sensitivity\n  volume_multiplier: 1.0\n",
            encoding="utf-8",
        )

        with patch("core.infra.config.get_user_config_path", return_value=dummy_yaml):
            update_yaml_float_setting(
                "voice_activation", "threshold", 0.65, subsection="wake_word"
            )
            update_yaml_float_setting(
                "voice_activation", "volume_multiplier", 1.3, precision=2
            )

            content = dummy_yaml.read_text(encoding="utf-8")
            assert "threshold: 0.65" in content
            assert "volume_multiplier: 1.30" in content


class TestSafeSlider:
    """Tests SafeSlider protection against hover and wheel modifications."""

    def test_safe_slider_ignores_hover_and_wheel(self) -> None:
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent, QWheelEvent
        from PySide6.QtWidgets import QApplication

        from core.ui.widgets.safe_slider import SafeSlider

        _ = QApplication.instance() or QApplication([])
        slider = SafeSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)

        # Hover move (no buttons pressed) must NOT change value
        hover_ev = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(80.0, 10.0),
            QPointF(80.0, 10.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        slider.mouseMoveEvent(hover_ev)
        assert slider.value() == 50

        # Wheel scroll must NOT change value
        wheel_ev = QWheelEvent(
            QPoint(80, 10),
            QPoint(80, 10),
            QPoint(0, 120),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        slider.wheelEvent(wheel_ev)
        assert slider.value() == 50
