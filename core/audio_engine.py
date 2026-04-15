import os
import time
import glob
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
    """Loads openWakeWord models based on configuration wakewords."""
    wakewords = config.get('wakewords', {})
    if not wakewords:
        logger.error("No wakewords found in config!")
        return None, []
        
    target_wakewords = list(wakewords.keys())
    
    # Pre-trained paths
    pretrained_paths = openwakeword.get_pretrained_model_paths()
    
    # Custom paths from models/
    custom_paths = glob.glob(os.path.join("models", "*.tflite"))
    
    all_available_paths = pretrained_paths + custom_paths
    
    selected_paths = []
    loaded_names = []
    
    for ww_name in target_wakewords:
        # Find path that contains the wakeword name
        found = False
        for p in all_available_paths:
            if ww_name in os.path.basename(p):
                selected_paths.append(p)
                loaded_names.append(ww_name)
                found = True
                break
                
        if not found:
            logger.warning(f"Model for wakeword '{ww_name}' not found in pretrained or models/ folder. It will be ignored.")
            
    if not selected_paths:
        logger.error("No valid models found to load. Falling back to default hey_jarvis if possible.")
        fallback = [p for p in pretrained_paths if "hey_jarvis" in p]
        if fallback:
            return Model(wakeword_model_paths=fallback), ["hey_jarvis"]
        return None, []
        
    logger.info(f"Loading wakeword models: {loaded_names}")
    return Model(wakeword_model_paths=selected_paths), loaded_names

def record_command_audio(stream, max_seconds=10, silence_duration=1.5, silence_threshold=15.0):
    logger.info("Recording command...")
    frames = []
    start_time = time.time()
    silence_start = None
    
    while time.time() - start_time < max_seconds:
        try:
            data = stream.read(1280, exception_on_overflow=False)
            frames.append(data)
            pcm = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
            
            if rms < silence_threshold:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > silence_duration:
                    logger.info("Silence detected. Stopping recording.")
                    break
            else:
                silence_start = None
        except Exception as e:
            logger.error(f"Error recording audio: {e}")
            break
            
    return b"".join(frames)