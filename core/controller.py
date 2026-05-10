import time
import numpy as np
import logging
import queue
import threading
from core.state import state_manager, JarvisState
from core.stt_engine import stt_engine
from core.utils import normalize_text
from core.job_queue import Job, JobType
from core.audio_engine import safe_reset_audio

logger = logging.getLogger(__name__)

class JarvisController:
    def __init__(self, config, automator, dispatcher, model, loaded_names, ui, tray, task_queue, stop_event, pa, stream):
        self.config = config
        self.automator = automator
        self.dispatcher = dispatcher
        self.model = model
        self.loaded_names = loaded_names
        self.ui = ui
        self.tray = tray
        self.task_queue = task_queue
        self.stop_event = stop_event
        self.pa = pa
        self.stream = stream

        # State Variables
        self.ignore_audio_until = 0
        self.cooldown = 0
        self.consecutive_zero_rms = 0
        self.command_frames = []
        self.confirmation_frames = []
        self.silence_start = None
        self.command_start_time = None

        # Constants from config or defaults
        self.volume_multiplier = config.get('jarvis', {}).get('volume_multiplier', 1.0)
        self.threshold = config.get('jarvis', {}).get('threshold', 0.4)
        self.cooldown_seconds = config.get('jarvis', {}).get('cooldown_seconds', 5)
        self.MAX_ZERO_RMS_BEFORE_RESET = 30

    def start(self):
        state_manager.add_callback(self._on_state_change)
        logger.info(f"Jarvis is listening for {self.loaded_names}...")

        try:
            with self.ui.get_live() as live:
                while not self.stop_event.is_set():
                    current_state = state_manager.get_state()
                    now = time.time()

                    # 1. Audio Processing
                    pcm, rms = self._read_audio()
                    if pcm is None:
                        continue
                    
                    self.ui.update(volume=pcm)

                    # Update ignore window if Jarvis is speaking
                    if self.automator.is_speaking:
                        self.ignore_audio_until = now + 0.4
                        self.model.reset()

                    # Self-healing: Check for dead silence
                    if self._check_dead_silence(rms):
                        continue

                    # 2. State-based Logic
                    if now < self.ignore_audio_until:
                        self.ui.update(status="Ignoring Audio (Self-Feedback)")
                        continue

                    if current_state == JarvisState.MUTED:
                        self.ui.update(status="MUTED/Sleeping")
                        continue

                    if current_state == JarvisState.CONFIRMING_DRY_RUN:
                        self._handle_confirmation(pcm, now)
                        continue

                    if current_state in (JarvisState.THINKING, JarvisState.EXECUTING, JarvisState.ERROR):
                        self._handle_busy_state(current_state)
                        continue

                    if current_state == JarvisState.LISTENING:
                        self._handle_listening(pcm, rms, now)
                        continue

                    if current_state == JarvisState.IDLE:
                        self._handle_idle(pcm, rms, now)

        except Exception as e:
            logger.error(f"Controller loop error: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _on_state_change(self, old_state, new_state, context):
        if new_state == JarvisState.CONFIRMING_DRY_RUN:
            self.ignore_audio_until = 0
            logger.info("Entering Confirmation: Listening immediately.")

        if (old_state == JarvisState.EXECUTING or old_state == JarvisState.CONFIRMING_DRY_RUN) and new_state == JarvisState.IDLE:
            logger.info(f"Transition {old_state.name} -> IDLE. Resetting buffers.")
            try:
                self.model.reset()
                self.ignore_audio_until = time.time() + 0.4
            except Exception as e:
                logger.error(f"Error during post-execution reset: {e}")

    def _read_audio(self):
        try:
            audio_data = self.stream.read(1280, exception_on_overflow=False)
            pcm = np.frombuffer(audio_data, dtype=np.int16)

            if self.volume_multiplier != 1.0:
                pcm = (pcm * self.volume_multiplier).clip(-32768, 32767).astype(np.int16)

            rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
            return pcm, rms
        except Exception as e:
            if not self.stop_event.is_set():
                logger.error(f"Microphone stream error: {e}. Resetting...")
                self.pa, self.stream = safe_reset_audio(self.pa, self.stream)
                self.dispatcher.audio_stream = self.stream
                time.sleep(1)
            return None, 0

    def _check_dead_silence(self, rms):
        if rms < 0.1:
            self.consecutive_zero_rms += 1
        else:
            self.consecutive_zero_rms = 0
            
        if self.consecutive_zero_rms > self.MAX_ZERO_RMS_BEFORE_RESET:
            logger.warning("Dead silence detected! Self-healing...")
            self.ui.update(status="Self-Healing...")
            self.pa, self.stream = safe_reset_audio(self.pa, self.stream)
            self.dispatcher.audio_stream = self.stream
            self.consecutive_zero_rms = 0
            self.model.reset()
            return True
        return False

    def _handle_confirmation(self, pcm, now):
        self.ui.update(status="Aguardando Confirmação...")
        self.confirmation_frames.append(pcm.tobytes())
        
        if len(self.confirmation_frames) > 10: 
            audio_chunk = b"".join(self.confirmation_frames)
            self.confirmation_frames = [] 
            
            try:
                text = stt_engine.transcribe(audio_chunk)
                norm = normalize_text(text)
                if any(word in norm for word in ["sim", "confirma", "pode", "autorizo", "yes", "vai"]):
                    logger.info("Voice confirmation: APPROVED")
                    if self.dispatcher.active_dialog:
                        self.dispatcher.active_dialog.approve()
                    self.ignore_audio_until = now + 0.3
                elif any(word in norm for word in ["nao", "não", "cancela", "aborta", "no"]):
                    logger.info("Voice confirmation: REJECTED")
                    if self.dispatcher.active_dialog:
                        self.dispatcher.active_dialog.reject()
                    self.ignore_audio_until = now + 0.3
            except Exception as e:
                logger.error(f"STT Error during confirmation: {e}")

    def _handle_busy_state(self, current_state):
        status_map = {
            JarvisState.THINKING: "Processando...",
            JarvisState.EXECUTING: "Executando...",
            JarvisState.ERROR: "Erro Detectado!"
        }
        self.ui.update(status=status_map.get(current_state, "Ocupado"))

    def _handle_listening(self, pcm, rms, now):
        self.ui.update(status="Gravando...")
        self.command_frames.append(pcm.tobytes())
        
        stop_recording = False
        if rms < 15.0:
            if self.silence_start is None:
                self.silence_start = now
            elif now - self.silence_start > 1.5:
                stop_recording = True
        else:
            self.silence_start = None
            
        if now - self.command_start_time > 10.0:
            logger.warning("Listening timeout reached.")
            stop_recording = True

        if stop_recording:
            audio_bytes = b"".join(self.command_frames)
            state_manager.set_state(JarvisState.THINKING)
            self.task_queue.put(Job(type=JobType.LLM_DYNAMIC, payload=audio_bytes))
            self.command_frames = []
            self.silence_start = None

    def _handle_idle(self, pcm, rms, now):
        self.ui.update(status="Listening" if now > self.cooldown else "Cooldown")
        
        highest_score = 0.0
        detected_wakeword = None
        
        if rms > 20 and now > self.cooldown: 
            prediction = self.model.predict(pcm)
            for model_key, score in prediction.items():
                if score > highest_score:
                    highest_score = float(score)
                    detected_wakeword = model_key
                    
            if highest_score > 0.1:
                logger.debug(f"Prediction debug (RMS: {rms:.1f}): {prediction}")
        
        self.ui.update(score=highest_score)

        if highest_score > self.threshold:
            ww_name_clean = next((n for n in self.loaded_names if n in detected_wakeword), detected_wakeword)
            logger.info(f"Wake word '{ww_name_clean}' detected! (Score: {highest_score:.2f})")
            
            if ww_name_clean == 'hey_jarvis':
                self.automator.speak("Sim?")
                state_manager.set_state(JarvisState.LISTENING)
                self.command_frames = []
                self.confirmation_frames = []
                self.silence_start = None
                self.command_start_time = now
            else:
                self.automator.speak("Sim?")
                self.task_queue.put(Job(type=JobType.WAKEWORD, payload=(ww_name_clean, highest_score)))
                state_manager.set_state(JarvisState.EXECUTING)
            
            self.cooldown = now + self.cooldown_seconds

    def _cleanup(self):
        logger.info("Cleaning up controller...")
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
        except:
            pass
