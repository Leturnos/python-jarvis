"""Thread-safe synchronization helpers for PortAudio initialization and teardown.

PortAudio's C functions Pa_Initialize() and Pa_Terminate() are not thread-safe on
Windows and can raise an Access Violation (0xC0000005) when invoked concurrently
from multiple threads (e.g., audio input stream setup and TTS worker startup).
"""

import threading
from typing import Any

import pyaudio

PORTAUDIO_LOCK = threading.RLock()


def create_pyaudio() -> pyaudio.PyAudio:
    """Instantiate pyaudio.PyAudio serialized under PORTAUDIO_LOCK."""
    with PORTAUDIO_LOCK:
        return pyaudio.PyAudio()


def terminate_pyaudio(pa: Any) -> None:
    """Terminate a PyAudio instance serialized under PORTAUDIO_LOCK."""
    if pa is None:
        return
    with PORTAUDIO_LOCK:
        pa.terminate()
