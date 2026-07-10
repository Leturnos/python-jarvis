import logging
import queue
import threading
import time
from typing import Any

import numpy as np

from core.activation import ActivationActionType, ActivationContext, ActivationManager
from core.audio.stt_engine import stt_engine
from core.execution.job_queue import Job, JobType
from core.runtime.state import JarvisState, state_manager
from core.shared.utils import normalize_text
from core.shared.voice_responses import CONFIRMATION_APPROVALS, CONFIRMATION_REJECTIONS

logger = logging.getLogger(__name__)


class JarvisController:
    """Main orchestration controller for the Jarvis assistant.

    This class manages the real-time audio processing loop, coordinates state
    transitions, handles wake word detection, and manages audio buffers for
    commands and confirmations. It acts as the bridge between the audio hardware
    and the higher-level logic (STT, LLM, Dispatcher).

    Attributes:
        config (dict): Configuration parameters.
        automator (WarpAutomator): Helper for speech and UI automation.
        dispatcher (ActionDispatcher): Hub for routing and executing actions.
        model (openwakeword.Model): The loaded wake word detection model.
        loaded_names (list): List of wake word names the model is listening for.
        ui (JarvisUI): Interface for real-time visual feedback.
        tray (JarvisTray): System tray integration.
        task_queue (queue.Queue): Queue for background command execution.
        stop_event (threading.Event): Signal to stop the controller loop.
        pa: PyAudio instance.
        stream: PyAudio input stream.
    """

    def __init__(
        self,
        config: dict[str, Any],
        tts_engine: Any,
        dispatcher: Any,
        model: Any,
        loaded_names: list[str],
        ui: Any,
        tray: Any,
        task_queue: queue.Queue[Any],
        stop_event: threading.Event,
        pa: Any,
        stream: Any,
    ) -> None:
        """Initializes the controller with injected dependencies.

        Args:
            config, tts_engine, dispatcher, model, loaded_names, ui, tray,
            task_queue, stop_event, pa, stream: Dependencies required for
            orchestration.
        """
        self.config = config
        self.tts_engine = tts_engine
        self.dispatcher = dispatcher
        self.model = model
        self.loaded_names = loaded_names
        self.ui = ui
        self.tray = tray
        self.task_queue = task_queue
        self.stop_event = stop_event

        # AudioLoopManager handles PyAudio lifecycle
        from core.audio.audio_loop import AudioLoopManager

        self.audio_manager = AudioLoopManager(
            config=config,
            dispatcher=dispatcher,
            ui=ui,
            pa=pa,
            stream=stream,
            stop_event=stop_event,
        )

        # Activation Manager
        self.activation_manager = ActivationManager(config)

        # State Variables
        self.ignore_audio_until = 0.0
        self.cooldown = 0
        self.command_frames: list[bytes] = []
        self.confirmation_frames: list[bytes] = []
        self.silence_start: float | None = None
        self.command_start_time: float | None = None

        # Constants from config or defaults
        self.threshold = config.get("jarvis", {}).get("threshold", 0.4)
        self.cooldown_seconds = config.get("jarvis", {}).get("cooldown_seconds", 5)

    def start(self) -> None:
        """Starts the main orchestration loop.

        This method enters an infinite loop (until stop_event is set) that
        reads audio, calculates volume (RMS), updates the UI, and delegates
        processing based on the current system state.
        """
        state_manager.add_callback(self._on_state_change)
        logger.info(f"Jarvis is listening for {self.loaded_names}...")

        try:
            with self.ui.get_live():
                while not self.stop_event.is_set():
                    current_state = state_manager.get_state()
                    now = time.time()

                    # 1. Update Tray Timer and Auto-resume check
                    if self.tray:
                        # is_muted() in Tray class handles auto-resuming to IDLE when timer expires
                        self.tray.is_muted()

                    # 2. Audio Processing via isolated AudioManager
                    pcm, rms = self.audio_manager.read_frame()
                    if pcm is None:
                        continue

                    self.ui.update(volume=pcm)

                    # Update ignore window if Jarvis is speaking
                    if self.tts_engine.is_speaking:
                        self.ignore_audio_until = now + 0.4
                        self.model.reset()

                    # Self-healing check using isolated AudioManager
                    if self.audio_manager.check_dead_silence(rms, self.model):
                        continue

                    # 3. Activation Gate Evaluation
                    # Gather context for decision making
                    context = ActivationContext(
                        wakeword_score=0.0,  # Will be filled in _handle_idle if needed
                        wakeword_detected=None,
                        is_fullscreen=self.activation_manager.is_fullscreen(),
                        is_hotkey_pressed=self.activation_manager.is_hotkey_pressed(),
                        current_state=current_state,
                        timestamp=now,
                    )

                    # 4. State-based Logic
                    if now < self.ignore_audio_until:
                        self.ui.update(status="Ignoring Audio (Self-Feedback)")
                        continue

                    if current_state == JarvisState.MUTED:
                        self.ui.update(status="MUTED")
                        continue

                    if current_state == JarvisState.SLEEPING:
                        self.ui.update(status="SLEEPING")

                        # Allow waking up via PTT
                        action_obj = self.activation_manager.evaluate(context)
                        if (
                            action_obj.action_type
                            == ActivationActionType.TRIGGER_PTT_START
                        ):
                            logger.info("Waking up from Sleep via PTT!")
                            self.tray.mute_until = 0  # Clear timer if any
                            stt_engine.load()  # Preload model before listening
                            self.tts_engine.speak("Sim?")
                            state_manager.set_state(JarvisState.LISTENING)
                            self.command_frames = []
                            self.confirmation_frames = []
                            self.silence_start = None
                            self.command_start_time = context.timestamp
                        continue

                    if current_state == JarvisState.SUSPENDED:
                        self._handle_suspended(context)
                        continue

                    if current_state == JarvisState.CONFIRMING_DRY_RUN:
                        self._handle_confirmation(pcm, now)
                        continue

                    if current_state in (
                        JarvisState.THINKING,
                        JarvisState.EXECUTING,
                        JarvisState.ERROR,
                    ):
                        self._handle_busy_state(current_state)
                        continue

                    if current_state == JarvisState.LISTENING:
                        # PTT Check: if we are in PTT hold mode and key is released, stop
                        action_obj = self.activation_manager.evaluate(context)
                        if (
                            action_obj.action_type
                            == ActivationActionType.TRIGGER_PTT_STOP
                        ):
                            self._stop_listening_and_process(now)
                            continue

                        self._handle_listening(pcm, rms, now)
                        continue

                    if current_state == JarvisState.IDLE:
                        self._handle_idle(pcm, rms, context)

        except Exception as e:
            logger.error(f"Controller loop error: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _on_state_change(
        self,
        old_state: JarvisState,
        new_state: JarvisState,
        context: dict[str, Any] | None,
    ) -> None:
        # 1. Resource Management (Memory Optimization)
        if new_state == JarvisState.MUTED:
            # Unload heavy models when entering muted state
            stt_engine.unload()
        elif old_state == JarvisState.MUTED and new_state == JarvisState.IDLE:
            # Proactively reload models when coming back from muted state
            stt_engine.load()

        # 2. State-specific Logic
        if new_state == JarvisState.CONFIRMING_DRY_RUN:
            self.ignore_audio_until = 0
            logger.info("Entering Confirmation: Listening immediately.")

        if (
            old_state == JarvisState.EXECUTING
            or old_state == JarvisState.CONFIRMING_DRY_RUN
        ) and new_state == JarvisState.IDLE:
            logger.info(f"Transition {old_state.name} -> IDLE. Resetting buffers.")
            try:
                self.model.reset()
                self.ignore_audio_until = time.time() + 0.4
            except Exception as e:
                logger.error(f"Error during post-execution reset: {e}")

    def _handle_confirmation(self, pcm: np.ndarray, now: float) -> None:
        self.ui.update(status="Aguardando Confirmação...")
        self.confirmation_frames.append(pcm.tobytes())

        if len(self.confirmation_frames) > 10:
            audio_chunk = b"".join(self.confirmation_frames)
            self.confirmation_frames = []

            try:
                text = stt_engine.transcribe(audio_chunk)
                norm = normalize_text(text)
                if any(word in norm for word in CONFIRMATION_APPROVALS):
                    logger.info("Voice confirmation: APPROVED")
                    if self.dispatcher.active_dialog:
                        self.dispatcher.active_dialog.approve()
                    self.ignore_audio_until = now + 0.3
                elif any(word in norm for word in CONFIRMATION_REJECTIONS):
                    logger.info("Voice confirmation: REJECTED")
                    if self.dispatcher.active_dialog:
                        self.dispatcher.active_dialog.reject()
                    self.ignore_audio_until = now + 0.3
            except Exception as e:
                logger.error(f"STT Error during confirmation: {e}")

    def _handle_busy_state(self, current_state: JarvisState) -> None:
        status_map = {
            JarvisState.THINKING: "Processando...",
            JarvisState.EXECUTING: "Executando...",
            JarvisState.ERROR: "Erro Detectado!",
        }
        self.ui.update(status=status_map.get(current_state, "Ocupado"))

    def _handle_listening(self, pcm: np.ndarray, rms: float, now: float) -> None:
        self.ui.update(status="Gravando...")
        self.command_frames.append(pcm.tobytes())

        stop_recording = False
        silence_rms_threshold = (
            self.config.get("voice_activation", {})
            .get("thresholds", {})
            .get("silence_rms", 15.0)
        )
        silence_end_timeout = (
            self.config.get("voice_activation", {})
            .get("timeouts", {})
            .get("silence_end_seconds", 1.5)
        )
        max_listening_timeout = (
            self.config.get("voice_activation", {})
            .get("timeouts", {})
            .get("max_listening_seconds", 10.0)
        )

        if rms < silence_rms_threshold:
            if self.silence_start is None:
                self.silence_start = now
            elif now - self.silence_start > silence_end_timeout:
                stop_recording = True
        else:
            self.silence_start = None

        if (
            self.command_start_time is not None
            and now - self.command_start_time > max_listening_timeout
        ):
            logger.warning("Listening timeout reached.")
            stop_recording = True

        if stop_recording:
            self._stop_listening_and_process(now)

    def _stop_listening_and_process(self, now: float) -> None:
        audio_bytes = b"".join(self.command_frames)
        state_manager.set_state(JarvisState.THINKING)
        self.task_queue.put(Job(type=JobType.LLM_DYNAMIC, payload=audio_bytes))
        self.command_frames = []
        self.silence_start = None

    def _handle_suspended(self, context: ActivationContext) -> None:
        self.ui.update(status="SUSPENDED (Fullscreen)")
        action_obj = self.activation_manager.evaluate(context)
        if action_obj.action_type == ActivationActionType.RESUME:
            logger.info("Fullscreen app closed/minimized. Resuming to IDLE.")
            state_manager.set_state(JarvisState.IDLE)

    def _handle_idle(
        self, pcm: np.ndarray, rms: float, context: ActivationContext
    ) -> None:
        self.ui.update(
            status="Listening" if context.timestamp > self.cooldown else "Cooldown"
        )

        highest_score = 0.0
        detected_wakeword = None
        speech_rms_threshold = (
            self.config.get("voice_activation", {})
            .get("thresholds", {})
            .get("speech_rms", 20.0)
        )

        if rms > speech_rms_threshold and context.timestamp > self.cooldown:
            prediction = self.model.predict(pcm)
            for model_key, score in prediction.items():
                if score > highest_score:
                    highest_score = float(score)
                    detected_wakeword = model_key

            if highest_score > 0.1:
                logger.debug(f"Prediction debug (RMS: {rms:.1f}): {prediction}")

        self.ui.update(score=highest_score)

        # Clean the wake word name (e.g., 'hey_jarvis_v0.1' -> 'hey_jarvis')
        ww_name_clean = None
        if detected_wakeword:
            ww_name_clean = next(
                (n for n in self.loaded_names if n in detected_wakeword),
                detected_wakeword,
            )

        # Update context with wake word info before delegation
        context.wakeword_score = highest_score
        context.wakeword_detected = ww_name_clean

        # Delegate activation decision to Manager
        action_obj = self.activation_manager.evaluate(context)

        if action_obj.action_type == ActivationActionType.SUSPEND:
            state_manager.set_state(JarvisState.SUSPENDED)
            return

        if action_obj.action_type in (
            ActivationActionType.TRIGGER_WAKE,
            ActivationActionType.TRIGGER_PTT_START,
        ):
            source = action_obj.source
            if source == "WAKE_WORD":
                ww_name_clean = context.wakeword_detected
                logger.info(
                    f"Wake word '{ww_name_clean}' detected! (Score: {highest_score:.2f})"
                )

                if ww_name_clean == "hey_jarvis":
                    self.tts_engine.speak("Sim?")
                    state_manager.set_state(JarvisState.LISTENING)
                    self.command_frames = []
                    self.confirmation_frames = []
                    self.silence_start = None
                    self.command_start_time = context.timestamp
                else:
                    self.tts_engine.speak("Sim?")
                    self.task_queue.put(
                        Job(
                            type=JobType.WAKEWORD,
                            payload=(ww_name_clean, highest_score),
                        )
                    )
                    state_manager.set_state(JarvisState.EXECUTING)

            elif source == "PTT":
                logger.info("PTT Activation triggered!")
                self.tts_engine.speak("Sim?")
                state_manager.set_state(JarvisState.LISTENING)
                self.command_frames = []
                self.confirmation_frames = []
                self.silence_start = None
                self.command_start_time = context.timestamp

            self.cooldown = context.timestamp + self.cooldown_seconds

    def _cleanup(self) -> None:
        self.audio_manager.cleanup()
