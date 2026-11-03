import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SimpleCardWidget,
    StrongBodyLabel,
)

from core.infra.config import config, update_yaml_float_setting
from core.infra.logger_config import logger
from core.runtime.state import JarvisState, state_manager


class AudioCalibrationDialog(QDialog):
    """Refined 3-step interactive calibration wizard for microphone gain and wake word sensitivity.

    Guides the user to speak 'Hey Jarvis' 3 times, samples live openWakeWord scores and
    audio RMS values, calculates optimal threshold and volume multiplier recommendations,
    and displays the calibrated settings with live testing before applying.
    """

    TOTAL_STEPS = 3

    def __init__(
        self,
        ui_adapter: Any = None,
        on_apply: Callable[[float, float, float], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ui_adapter = ui_adapter
        self.on_apply = on_apply

        self.current_step = 0  # 0: intro, 1..3: sampling, 4: results/test
        self.samples: list[dict[str, float]] = []  # [{score, rms}, ...]
        self._step_cooldown_until: float = 0.0

        self._current_utterance_max_score: float = 0.0
        self._current_utterance_max_rms: float = 0.0
        self._is_utterance_active: bool = False
        self._test_feedback_timer: QTimer | None = None
        self._is_test_detected: bool = False
        self._previous_state: JarvisState = JarvisState.IDLE

        va_conf = config.get("voice_activation", {})
        ww_conf = va_conf.get("wake_word", {})

        self.current_threshold = float(
            ww_conf.get("threshold", config.get("jarvis", {}).get("threshold", 0.50))
        )
        self.current_volume_multiplier = float(
            va_conf.get(
                "volume_multiplier",
                config.get("jarvis", {}).get("volume_multiplier", 1.0),
            )
        )
        self.current_speech_rms = float(
            va_conf.get("thresholds", {}).get("speech_rms", 20.0)
        )

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Jarvis - Calibração de Microfone & Wake Word")
        self.setFixedWidth(560)
        self.setMinimumHeight(490)
        self.setModal(True)
        self.setStyleSheet(
            "QDialog { background-color: #202023; color: #ffffff; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title = StrongBodyLabel("🎙️ Calibração de Microfone & Ativação", self)
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = CaptionLabel(
            "Ajuste automático de sensibilidade e ganho do microfone em 3 passos.", self
        )
        subtitle.setStyleSheet("color: #8e8e99; font-size: 12px;")
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # Main Card
        self.main_card = SimpleCardWidget(self)
        self.main_card.setStyleSheet(
            "SimpleCardWidget { background-color: #28282c; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(self.main_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        # Step Indicator Header
        self.step_label = StrongBodyLabel("Preparação", self.main_card)
        self.step_label.setStyleSheet("color: #4cc2ff; font-size: 14px;")
        card_layout.addWidget(self.step_label)

        # Instruction Text
        self.instruction_label = BodyLabel(
            "Clique no botão abaixo para iniciar. O assistente pedirá para você "
            "falar 'Hey Jarvis' 3 vezes em sua distância e entonação habituais.",
            self.main_card,
        )
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setStyleSheet("color: #d1d1d6; font-size: 13px;")
        card_layout.addWidget(self.instruction_label)

        # Real-time Volume Meter (VU Meter)
        vu_box = QVBoxLayout()
        vu_box.setSpacing(4)
        vu_header = QHBoxLayout()
        vu_title = CaptionLabel("Nível do Microfone (Volume / RMS):", self.main_card)
        vu_title.setStyleSheet("color: #9e9ea7;")
        self.vu_val_label = CaptionLabel("0 RMS", self.main_card)
        self.vu_val_label.setStyleSheet("color: #9e9ea7;")
        vu_header.addWidget(vu_title)
        vu_header.addStretch(1)
        vu_header.addWidget(self.vu_val_label)
        vu_box.addLayout(vu_header)

        self.vu_meter = ProgressBar(self.main_card)
        self.vu_meter.setRange(0, 100)
        self.vu_meter.setValue(0)
        self.vu_meter.setFixedHeight(8)
        vu_box.addWidget(self.vu_meter)
        card_layout.addLayout(vu_box)

        # Real-time Wake Word Score Meter
        score_box = QVBoxLayout()
        score_box.setSpacing(4)
        score_header = QHBoxLayout()
        score_title = CaptionLabel("Confiança do Hey Jarvis (Score):", self.main_card)
        score_title.setStyleSheet("color: #9e9ea7;")
        self.score_val_label = CaptionLabel("0.00", self.main_card)
        self.score_val_label.setStyleSheet("color: #9e9ea7;")
        score_header.addWidget(score_title)
        score_header.addStretch(1)
        score_header.addWidget(self.score_val_label)
        score_box.addLayout(score_header)

        self.score_meter = ProgressBar(self.main_card)
        self.score_meter.setRange(0, 100)
        self.score_meter.setValue(0)
        self.score_meter.setFixedHeight(8)
        score_box.addWidget(self.score_meter)
        card_layout.addLayout(score_box)

        # Utterance Feedback Badge (Step 1-3)
        self.badge_frame = QFrame(self.main_card)
        self.badge_frame.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.04); border-radius: 6px; padding: 6px;"
        )
        badge_layout = QHBoxLayout(self.badge_frame)
        badge_layout.setContentsMargins(10, 6, 10, 6)
        self.badge_label = CaptionLabel("Aguardando início...", self.badge_frame)
        self.badge_label.setStyleSheet("color: #9e9ea7; font-weight: 500;")
        badge_layout.addWidget(self.badge_label)
        card_layout.addWidget(self.badge_frame)

        # Dynamic Results Area (Step 4 - Conclusão & Teste)
        self.results_container = QWidget(self.main_card)
        res_layout = QVBoxLayout(self.results_container)
        res_layout.setContentsMargins(0, 2, 0, 0)
        res_layout.setSpacing(10)

        # Summary of attempts
        self.summary_samples_label = CaptionLabel("", self.results_container)
        self.summary_samples_label.setWordWrap(True)
        self.summary_samples_label.setStyleSheet(
            "color: #4cc2ff; font-size: 12px; font-weight: 500;"
        )
        res_layout.addWidget(self.summary_samples_label)

        # Calibrated Recommendation Display Card
        rec_card = QFrame(self.results_container)
        rec_card.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.03); "
            "border: 1px solid rgba(255, 255, 255, 0.07); "
            "border-radius: 6px;"
        )
        rec_layout = QVBoxLayout(rec_card)
        rec_layout.setContentsMargins(12, 10, 12, 10)
        rec_layout.setSpacing(8)

        # Row 1: Threshold
        th_row = QHBoxLayout()
        th_title = BodyLabel("Sensibilidade Wake Word Recomendada:", rec_card)
        self.th_val_label = StrongBodyLabel(f"{self.current_threshold:.2f}", rec_card)
        self.th_val_label.setStyleSheet("color: #4cc2ff; font-weight: 600;")
        th_row.addWidget(th_title)
        th_row.addStretch(1)
        th_row.addWidget(self.th_val_label)
        rec_layout.addLayout(th_row)

        # Row 2: Volume Multiplier
        gain_row = QHBoxLayout()
        gain_title = BodyLabel("Ganho do Microfone Recomendado:", rec_card)
        self.gain_val_label = StrongBodyLabel(
            f"{self.current_volume_multiplier:.1f}x", rec_card
        )
        self.gain_val_label.setStyleSheet("color: #4cc2ff; font-weight: 600;")
        gain_row.addWidget(gain_title)
        gain_row.addStretch(1)
        gain_row.addWidget(self.gain_val_label)
        rec_layout.addLayout(gain_row)

        res_layout.addWidget(rec_card)

        # Test Detection Banner
        self.test_banner = QLabel("🎤 Fale 'Hey Jarvis' agora para testar...", self)
        self.test_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_banner.setFixedHeight(38)
        self.test_banner.setStyleSheet(
            "background-color: #323238; color: #d1d1d6; border-radius: 6px; padding: 6px; font-weight: 500;"
        )
        res_layout.addWidget(self.test_banner)

        card_layout.addWidget(self.results_container)
        self.results_container.setVisible(False)

        layout.addWidget(self.main_card)

        # Action Buttons Footer
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.secondary_btn = PushButton("Cancelar", self)
        self.secondary_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.secondary_btn)

        btn_layout.addStretch(1)

        self.primary_btn = PrimaryPushButton("Começar Calibração", self)
        self.primary_btn.clicked.connect(self._on_primary_action)
        btn_layout.addWidget(self.primary_btn)

        layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        if hasattr(self.ui_adapter, "calibration_data_updated"):
            self.ui_adapter.calibration_data_updated.connect(self._on_audio_data)

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Enters CALIBRATING state when opened to mute standard activation responses."""
        super().showEvent(event)
        try:
            current_st = state_manager.get_state()
            if current_st != JarvisState.CALIBRATING:
                self._previous_state = current_st
            state_manager.set_state(JarvisState.CALIBRATING)
        except Exception as e:
            logger.warning(f"Could not transition to CALIBRATING: {e}")

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Returns to IDLE state upon closing."""
        self._ensure_idle_state()
        super().closeEvent(event)

    def reject(self) -> None:
        """Handles cancel / escape key."""
        self._ensure_idle_state()
        super().reject()

    def _ensure_idle_state(self) -> None:
        if self._test_feedback_timer is not None:
            try:
                self._test_feedback_timer.stop()
            except Exception:
                pass

        try:
            if hasattr(self.ui_adapter, "calibration_data_updated"):
                try:
                    self.ui_adapter.calibration_data_updated.disconnect(
                        self._on_audio_data
                    )
                except (RuntimeError, TypeError):
                    pass
        except Exception as e:
            logger.debug(f"Error disconnecting calibration signal: {e}")

        try:
            if state_manager.get_state() == JarvisState.CALIBRATING:
                target_state = (
                    JarvisState.MUTED
                    if self._previous_state == JarvisState.MUTED
                    else JarvisState.IDLE
                )
                state_manager.set_state(target_state)
        except Exception as e:
            logger.debug(f"Error restoring IDLE/MUTED state: {e}")

    def _on_primary_action(self) -> None:
        if self.current_step == 0:
            # Start Step 1
            self._start_step(1)
        elif self.current_step in (1, 2, 3):
            # Manual sample capture fallback if user prefers button
            if self._current_utterance_max_score > 0.15:
                self._record_sample(
                    max(0.35, self._current_utterance_max_score),
                    max(15.0, self._current_utterance_max_rms),
                )
            else:
                self.badge_label.setText("⚠️ Fale 'Hey Jarvis' antes de avançar.")
        elif self.current_step == 4:
            # Save and Apply
            self._apply_and_save()

    def _start_step(self, step_number: int) -> None:
        self.current_step = step_number
        self._current_utterance_max_score = 0.0
        self._current_utterance_max_rms = 0.0
        self._is_utterance_active = False
        self._step_cooldown_until = time.time() + 0.6

        self.step_label.setText(f"Etapa {step_number} de {self.TOTAL_STEPS}")
        self.instruction_label.setText(
            f"Fale 'Hey Jarvis' agora ({step_number}/{self.TOTAL_STEPS}) em sua entonação natural e clara..."
        )
        self.badge_label.setText("👂 Ouvindo microfone...")
        self.badge_label.setStyleSheet("color: #4cc2ff; font-weight: 500;")
        self.primary_btn.setText(f"Avançar ({step_number}/{self.TOTAL_STEPS})")
        self.secondary_btn.setText("Cancelar")

    def _reset_test_banner(self) -> None:
        self._is_test_detected = False
        self.test_banner.setText("🎤 Fale 'Hey Jarvis' agora para testar...")
        self.test_banner.setStyleSheet(
            "background-color: #323238; color: #d1d1d6; border-radius: 6px; padding: 6px; font-weight: 500;"
        )

    def _on_audio_data(self, score: float, rms: float) -> None:
        # Update live meters
        vu_val = min(100, int(rms * 1.5))
        self.vu_meter.setValue(vu_val)
        self.vu_val_label.setText(f"{rms:.1f} RMS")

        score_pct = int(score * 100)
        self.score_meter.setValue(score_pct)
        self.score_val_label.setText(f"{score:.2f}")

        now = time.time()

        # Step 4: Live Testing Mode
        if self.current_step == 4:
            if score >= self.current_threshold and rms >= max(
                10.0, self.current_speech_rms * 0.7
            ):
                if not self._is_test_detected:
                    self._is_test_detected = True
                    self.test_banner.setText(
                        f"✅ 'Hey Jarvis' detectado com sucesso! (Score: {score:.2f})"
                    )
                    self.test_banner.setStyleSheet(
                        "background-color: #107c41; color: #ffffff; border-radius: 6px; padding: 6px; font-weight: 600;"
                    )
                    if self._test_feedback_timer is not None:
                        self._test_feedback_timer.stop()
                    self._test_feedback_timer = QTimer(self)
                    self._test_feedback_timer.setSingleShot(True)
                    self._test_feedback_timer.timeout.connect(self._reset_test_banner)
                    self._test_feedback_timer.start(1000)
            return

        if self.current_step not in (1, 2, 3) or now < self._step_cooldown_until:
            return

        # Peak tracking during utterance
        if score > self._current_utterance_max_score:
            self._current_utterance_max_score = score
        if rms > self._current_utterance_max_rms:
            self._current_utterance_max_rms = rms

        # Speech activity detection
        if rms >= 15.0 or score >= 0.25:
            self._is_utterance_active = True
            self.badge_label.setText(
                f"Voz detectada! (Score atual: {score:.2f} | Volume: {rms:.0f})"
            )
            self.badge_label.setStyleSheet("color: #57d9a3; font-weight: 600;")
        elif self._is_utterance_active and rms < 12.0:
            # Utterance ended after peak
            if self._current_utterance_max_score >= 0.30:
                self._record_sample(
                    self._current_utterance_max_score, self._current_utterance_max_rms
                )
            else:
                # Silence resumed without reaching wakeword threshold; reset utterance state
                self._is_utterance_active = False
                self._current_utterance_max_score = 0.0
                self._current_utterance_max_rms = 0.0
                self.badge_label.setText("👂 Ouvindo microfone...")
                self.badge_label.setStyleSheet("color: #4cc2ff; font-weight: 500;")

    def _record_sample(self, peak_score: float, peak_rms: float) -> None:
        self.samples.append({"score": peak_score, "rms": peak_rms})
        logger.info(
            f"Calibration sample {len(self.samples)}: score={peak_score:.2f}, rms={peak_rms:.1f}"
        )
        self.badge_label.setText(
            f"✅ Fala {len(self.samples)} registrada! (Score: {peak_score:.2f}, RMS: {peak_rms:.0f})"
        )
        self.badge_label.setStyleSheet("color: #4cc2ff; font-weight: 600;")

        if len(self.samples) < self.TOTAL_STEPS:
            # Short delay before next step
            self._step_cooldown_until = time.time() + 1.2
            QTimer.singleShot(1000, lambda: self._start_step(len(self.samples) + 1))
        else:
            QTimer.singleShot(800, self._show_results)

    @staticmethod
    def calculate_recommendations(
        samples: list[dict[str, float]],
    ) -> dict[str, float]:
        """Calculates optimal threshold and gain multiplier based on audio samples."""
        if not samples:
            return {
                "threshold": 0.50,
                "volume_multiplier": 1.0,
                "speech_rms": 20.0,
            }

        scores = [s["score"] for s in samples]
        rms_vals = [s["rms"] for s in samples]

        min_score = min(scores)
        rec_threshold = round(min_score * 0.82, 2)
        rec_threshold = max(0.25, min(0.80, rec_threshold))

        mean_rms = sum(rms_vals) / len(rms_vals)
        if mean_rms < 20.0:
            rec_gain = 1.4
        elif mean_rms < 30.0:
            rec_gain = 1.2
        elif mean_rms > 120.0:
            rec_gain = 0.8
        else:
            rec_gain = 1.0

        rec_speech_rms = max(10.0, min(30.0, round(min(rms_vals) * 0.45, 1)))

        return {
            "threshold": rec_threshold,
            "volume_multiplier": rec_gain,
            "speech_rms": rec_speech_rms,
        }

    def _show_results(self) -> None:
        self.current_step = 4
        recs = self.calculate_recommendations(self.samples)

        self.step_label.setText("🎉 Calibração Concluída!")
        self.step_label.setStyleSheet("color: #57d9a3; font-size: 14px;")
        self.instruction_label.setText(
            "Configurações ideais calculadas com sucesso! Teste o comando 'Hey Jarvis' abaixo ou salve para aplicar."
        )

        sample_str = " • ".join(
            f"Fala {i + 1}: score {s['score']:.2f}" for i, s in enumerate(self.samples)
        )
        self.summary_samples_label.setText(f"Amostras analisadas: {sample_str}")

        # Update recommended values
        self.current_threshold = recs["threshold"]
        self.current_volume_multiplier = recs["volume_multiplier"]
        self.current_speech_rms = recs["speech_rms"]

        self.th_val_label.setText(f"{self.current_threshold:.2f}")
        self.gain_val_label.setText(f"{self.current_volume_multiplier:.1f}x")

        self._reset_test_banner()
        self.results_container.setVisible(True)
        self.badge_frame.setVisible(False)

        self.primary_btn.setText("Salvar e Aplicar")
        self.secondary_btn.setText("Recalibrar")
        self.secondary_btn.clicked.disconnect()
        self.secondary_btn.clicked.connect(self._restart_calibration)
        self.adjustSize()

    def _restart_calibration(self) -> None:
        self.samples = []
        self._reset_test_banner()
        self.results_container.setVisible(False)
        self.badge_frame.setVisible(True)
        self.secondary_btn.clicked.disconnect()
        self.secondary_btn.clicked.connect(self.reject)
        self.secondary_btn.setText("Cancelar")
        self._start_step(1)
        self.adjustSize()

    def _apply_and_save(self) -> None:
        chosen_threshold = self.current_threshold
        chosen_gain = self.current_volume_multiplier
        chosen_speech_rms = self.current_speech_rms

        # 1. Update YAML configuration
        try:
            update_yaml_float_setting(
                "voice_activation",
                "threshold",
                chosen_threshold,
                subsection="wake_word",
                precision=2,
            )
            update_yaml_float_setting(
                "voice_activation",
                "volume_multiplier",
                chosen_gain,
                precision=2,
            )
            update_yaml_float_setting(
                "voice_activation",
                "speech_rms",
                chosen_speech_rms,
                subsection="thresholds",
                precision=1,
            )
        except Exception as e:
            logger.error(f"Error persisting calibration to YAML: {e}")

        # 2. Apply live via callback to controller
        if self.on_apply:
            try:
                self.on_apply(chosen_threshold, chosen_gain, chosen_speech_rms)
            except Exception as e:
                logger.error(f"Error applying calibration live: {e}")

        self._ensure_idle_state()
        self.accept()
