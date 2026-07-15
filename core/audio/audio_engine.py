import glob
import os
import time
from typing import Any

import numpy as np
import openwakeword
import pyaudio
from openwakeword.model import Model

from core.infra.logger_config import logger


def get_audio_stream(
    config: dict[str, Any] | None = None,
) -> tuple[pyaudio.PyAudio, pyaudio.Stream]:
    """Initializes and returns the PyAudio stream."""
    if config is None:
        from core.infra.config import config as global_config

        config = global_config

    voice_act = config.get("voice_activation", {})
    device_index = voice_act.get("device_index")
    frames_per_buffer = voice_act.get("frames_per_buffer", 1280)

    pa = pyaudio.PyAudio()
    stream_kwargs = {
        "rate": 16000,
        "channels": 1,
        "format": pyaudio.paInt16,
        "input": True,
        "frames_per_buffer": frames_per_buffer,
    }
    if device_index is not None:
        stream_kwargs["input_device_index"] = int(device_index)

    stream = pa.open(**stream_kwargs)
    return pa, stream


def load_wakeword_model(
    config: dict[str, Any] | None = None,
) -> tuple[Model | None, list[str]]:
    """Loads openWakeWord models (defaults and custom from models/ folder)."""
    if config is None:
        from core.infra.config import config as global_config

        config = global_config

    voice_act = config.get("voice_activation", {})
    wake_word_config = voice_act.get("wake_word", {})
    keyword = wake_word_config.get("keyword", "hey_jarvis")

    # Pre-trained paths
    pretrained_paths = openwakeword.get_pretrained_model_paths()

    # Custom paths from models/
    custom_paths = glob.glob(os.path.join("models", "*.onnx"))

    pretrained_paths + custom_paths

    selected_paths = []
    loaded_names = []

    # Always load keyword
    for p in pretrained_paths:
        if keyword in os.path.basename(p):
            selected_paths.append(p)
            loaded_names.append(keyword)
            break

    # Load any user-provided models from 'models/' directory for offline shortcuts
    for p in custom_paths:
        name = os.path.splitext(os.path.basename(p))[0]
        if name not in loaded_names:
            selected_paths.append(p)
            loaded_names.append(name)

    if not selected_paths:
        logger.error("No valid models found to load.")
        return None, []

    logger.info(f"Loading wakeword models: {loaded_names}")
    return Model(wakeword_model_paths=selected_paths), loaded_names


def safe_reset_audio(
    pa: pyaudio.PyAudio | None,
    stream: pyaudio.Stream | None,
    config: dict[str, Any] | None = None,
) -> tuple[pyaudio.PyAudio, pyaudio.Stream]:
    """Deep cleanup and re-initialization of the PyAudio engine."""
    logger.info("Performing hard reset of the audio engine...")
    try:
        if stream:
            stream.stop_stream()
            stream.close()
        if pa:
            pa.terminate()
    except Exception as e:
        logger.error(f"Error during audio cleanup: {e}")

    time.sleep(1.0)  # Grace period for OS to release resources
    return get_audio_stream(config)


def record_command_audio(
    stream: pyaudio.Stream,
    max_seconds: int = 10,
    silence_duration: float = 1.5,
    silence_threshold: float = 15.0,
    stop_event: Any = None,
    volume_multiplier: float = 1.0,
) -> bytes:
    """Utility to record audio synchronously. Used by background threads (e.g. Security Dialog)."""
    logger.info("Recording command...")
    frames = []
    start_time = time.time()
    silence_start = None

    while time.time() - start_time < max_seconds:
        if stop_event and stop_event.is_set():
            logger.info("Stop event detected. Stopping recording.")
            break
        try:
            data = stream.read(1280, exception_on_overflow=False)
            pcm = np.frombuffer(data, dtype=np.int16)

            if volume_multiplier != 1.0:
                pcm = (pcm * volume_multiplier).clip(-32768, 32767).astype(np.int16)

            frames.append(pcm.tobytes())

            rms = np.sqrt(np.mean(pcm.astype(np.float32) ** 2))

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
