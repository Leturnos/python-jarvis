import gc

import numpy as np
from faster_whisper import WhisperModel

from core.infra.logger_config import logger
from core.shared.errors import TechnicalError


class STTEngine:
    def __init__(
        self, model_size: str | None = None, config_dict: dict | None = None
    ) -> None:
        if config_dict is None:
            from core.infra.config import config

            stt_conf = config.get("stt", {})
        else:
            stt_conf = config_dict.get("stt", {})

        self.model_size = (
            model_size if model_size is not None else stt_conf.get("model_size", "tiny")
        )
        if not self.model_size:
            self.model_size = "tiny"

        self.device = stt_conf.get("device", "cpu") or "cpu"
        self.compute_type = stt_conf.get("compute_type", "int8") or "int8"
        self.language = stt_conf.get("language", "pt") or "pt"

        self.model: WhisperModel | None = None
        self.load()

    def load(self) -> None:
        """Loads the Whisper model into memory if not already loaded."""
        if self.model is None:
            logger.info(
                f"Loading Faster Whisper model ({self.model_size}) on {self.device}..."
            )
            try:
                self.model = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except Exception as e:
                logger.error(f"Failed to load STT model: {e}")

    def unload(self) -> None:
        """Unloads the model and clears memory references."""
        if self.model is not None:
            logger.info(
                f"Unloading Faster Whisper model ({self.model_size}) to save resources..."
            )
            # Remove reference and backend objects
            self.model = None

            # Explicitly call garbage collector to free memory
            gc.collect()

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        try:
            # Ensure model is loaded (safety fallback)
            if self.model is None:
                self.load()
                if self.model is None:
                    return ""

            # Convert raw bytes to numpy float32 array normalized to [-1.0, 1.0]
            audio_np = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )

            logger.info("Transcribing audio with faster-whisper...")
            segments, info = self.model.transcribe(
                audio_np, beam_size=1, language=self.language
            )

            text = " ".join([segment.text for segment in segments]).strip()
            logger.info(f"Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            raise TechnicalError(f"STT processing failed: {e}") from e


stt_engine = STTEngine()
