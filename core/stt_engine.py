import numpy as np
import io
from faster_whisper import WhisperModel
from core.logger_config import logger

class STTEngine:
    def __init__(self, model_size="tiny"):
        logger.info(f"Loading Faster Whisper model ({model_size}) on CPU...")
        # device="cpu", compute_type="int8" is the fastest configuration without GPU
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    def transcribe(self, audio_bytes, sample_rate=16000):
        try:
            # Convert raw bytes to numpy float32 array normalized to [-1.0, 1.0]
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            logger.info("Transcribing audio with faster-whisper...")
            segments, info = self.model.transcribe(audio_np, beam_size=1, language="pt")
            
            text = " ".join([segment.text for segment in segments]).strip()
            logger.info(f"Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            return ""

stt_engine = STTEngine("tiny")