import pyaudio
import numpy as np
import openwakeword
from openwakeword.model import Model
from core.config import config
from core.logger_config import logger

def get_audio_stream():
    """Initializes and returns the PyAudio stream."""
    pa = pyaudio.PyAudio()
    stream = pa.open(
        rate=16000,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=1280
    )
    return pa, stream

def load_wakeword_model():
    """Loads the openWakeWord model based on configuration."""
    wakeword_name = config.get('wakeword_name', 'hey_jarvis')
    model_paths = openwakeword.get_pretrained_model_paths()
    hey_jarvis_path = [p for p in model_paths if wakeword_name in p]
    return Model(wakeword_model_paths=hey_jarvis_path), wakeword_name
