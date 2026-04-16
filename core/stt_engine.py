import whisper
import numpy as np
import io
import soundfile as sf
from core.logger_config import logger

class STTEngine:
    def __init__(self, model_size="tiny"):
        logger.info(f"Loading Whisper model ({model_size})...")
        # fp16=False for CPU compatibility by default
        self.model = whisper.load_model(model_size)
        
    def transcribe(self, audio_bytes, sample_rate=16000):
        try:
            # Convert raw bytes to numpy array
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            logger.info("Transcribing audio...")
            result = self.model.transcribe(audio_np, fp16=False, language="pt")
            text = result.get("text", "").strip()
            logger.info(f"Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            return ""

stt_engine = STTEngine("tiny")