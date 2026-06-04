import gc

import numpy as np
from faster_whisper import WhisperModel

from core.infra.logger_config import logger
from core.shared.errors import TechnicalError


class STTEngine:
    def __init__(self, model_size: str = "tiny") -> None:
        self.model_size = model_size
        self.model: WhisperModel | None = None
        # Lazy loading: we don't load in __init__ anymore,
        # or we could load once then allow unload.
        # For now, let's load it immediately to preserve startup behavior,
        # but through the new load() method.
        self.load()

    def load(self) -> None:
        """Loads the Whisper model into memory if not already loaded."""
        if self.model is None:
            logger.info(f"Loading Faster Whisper model ({self.model_size}) on CPU...")
            try:
                # device="cpu", compute_type="int8" is the fastest configuration without GPU
                self.model = WhisperModel(
                    self.model_size, device="cpu", compute_type="int8"
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
            segments, info = self.model.transcribe(audio_np, beam_size=1, language="pt")

            text = " ".join([segment.text for segment in segments]).strip()
            logger.info(f"Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            raise TechnicalError(f"STT processing failed: {e}") from e


stt_engine = STTEngine("tiny")
