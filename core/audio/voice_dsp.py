"""Real-time acoustic DSP filters for Jarvis and Friday holographic voice profiles.

Uses pure NumPy FFT and time-domain micro-delay operations with zero external
audio DSP dependencies.
"""

import numpy as np
from numpy.typing import NDArray


def _apply_spectral_eq_and_chorus(
    samples: NDArray[np.float32],
    sample_rate: int,
    highpass_hz: float,
    presence_center_hz: float,
    presence_bandwidth_hz: float,
    presence_gain: float,
    delay_ms: float,
    delay_mix: float,
    drive: float,
) -> NDArray[np.float32]:
    """Applies frequency-domain EQ, helmet micro-resonance delay, and soft saturation."""
    if samples.size == 0 or sample_rate <= 0:
        return samples.astype(np.float32, copy=False)

    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    peak_in = float(np.max(np.abs(mono)))
    if peak_in < 1e-6:
        return mono

    # 1. Spectral shaping via real FFT
    n = mono.size
    spectrum = np.fft.rfft(mono)
    freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate))

    # Smooth high-pass roll-off to remove muddy low-end rumble inside helmet comms
    hp_curve = 1.0 / (1.0 + (highpass_hz / np.maximum(freqs, 1.0)) ** 4)

    # Gaussian presence boost in upper-mid frequencies for holographic clarity
    presence_bell = 1.0 + presence_gain * np.exp(
        -0.5 * ((freqs - presence_center_hz) / max(presence_bandwidth_hz, 1.0)) ** 2
    )

    # Gentle roll-off above 8.5 kHz to avoid harsh sibilance
    lp_curve = 1.0 / (1.0 + (freqs / 8500.0) ** 6)

    shaped = np.fft.irfft(spectrum * hp_curve * presence_bell * lp_curve, n=n).astype(
        np.float32
    )

    # 2. Holographic micro-delay (short chamber / HUD visor reflection)
    if delay_ms > 0.0 and delay_mix > 0.0:
        delay_samples = max(1, int(round((delay_ms / 1000.0) * sample_rate)))
        if delay_samples < n:
            delayed = np.zeros_like(shaped)
            delayed[delay_samples:] = shaped[:-delay_samples]
            mixed = shaped + (delay_mix * delayed)
        else:
            mixed = shaped
    else:
        mixed = shaped

    # 3. Soft dynamic compression / saturation (tanh limiter)
    compressed = np.tanh(mixed * drive).astype(np.float32)

    # 4. Normalize back to clean headroom (-0.8 dBFS ~ 0.91 peak)
    peak_out = float(np.max(np.abs(compressed)))
    if peak_out > 1e-6:
        target_peak = min(0.92, max(peak_in, 0.75))
        compressed = compressed * (target_peak / peak_out)

    return np.clip(compressed, -1.0, 1.0).astype(np.float32)


def apply_jarvis_mk3_dsp(
    samples: NDArray[np.float32], sample_rate: int
) -> NDArray[np.float32]:
    """Applies the J.A.R.V.I.S. Mark III (Iron Man helmet/hologram) acoustic filter."""
    return _apply_spectral_eq_and_chorus(
        samples=samples,
        sample_rate=sample_rate,
        highpass_hz=125.0,
        presence_center_hz=2850.0,
        presence_bandwidth_hz=950.0,
        presence_gain=0.65,
        delay_ms=11.0,
        delay_mix=0.22,
        drive=1.35,
    )


def apply_friday_mk50_dsp(
    samples: NDArray[np.float32], sample_rate: int
) -> NDArray[np.float32]:
    """Applies the F.R.I.D.A.Y. Mark L (crystalline tactical HUD) acoustic filter."""
    return _apply_spectral_eq_and_chorus(
        samples=samples,
        sample_rate=sample_rate,
        highpass_hz=145.0,
        presence_center_hz=3300.0,
        presence_bandwidth_hz=1100.0,
        presence_gain=0.55,
        delay_ms=8.5,
        delay_mix=0.18,
        drive=1.25,
    )


def apply_voice_dsp(
    samples: NDArray[np.float32], sample_rate: int, dsp_profile: str
) -> NDArray[np.float32]:
    """Dispatches the requested DSP profile onto raw float32 PCM samples."""
    if dsp_profile == "jarvis_mk3":
        return apply_jarvis_mk3_dsp(samples, sample_rate)
    if dsp_profile == "friday_mk50":
        return apply_friday_mk50_dsp(samples, sample_rate)
    return np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
