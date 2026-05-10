"""Tests for `core.audio_utils`.

We don't invoke Whisper or silero-vad here — those need heavy weights. The
plain decode/resample logic is tested with synthetic WAV blobs.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from core.audio_utils import (
    TARGET_SAMPLE_RATE,
    _resample_linear,
    decode_audio_blob,
)


def _make_wav_blob(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode a numpy array as 16-bit PCM WAV in memory."""
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_decode_audio_blob_empty_raises() -> None:
    with pytest.raises(ValueError):
        decode_audio_blob(b"")


def test_decode_audio_blob_returns_16k_mono_float32() -> None:
    sr_in = 24_000
    duration = 1.0
    t = np.linspace(0.0, duration, int(sr_in * duration), endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    blob = _make_wav_blob(tone, sr_in)

    out = decode_audio_blob(blob)

    assert out.dtype == np.float32
    assert out.ndim == 1
    # Resampled length should be ~duration * 16_000, allow ±1% rounding slack.
    expected = int(duration * TARGET_SAMPLE_RATE)
    assert abs(len(out) - expected) <= max(2, expected // 100)


def test_decode_audio_blob_mixes_stereo_to_mono() -> None:
    sr = TARGET_SAMPLE_RATE
    samples = np.zeros((1000, 2), dtype=np.float32)
    samples[:, 0] = 0.5
    samples[:, 1] = -0.5  # average should be 0.0
    blob = _make_wav_blob(samples, sr)

    out = decode_audio_blob(blob)

    assert out.ndim == 1
    assert len(out) == 1000
    np.testing.assert_allclose(out, 0.0, atol=1e-3)


def test_resample_linear_is_identity_when_rates_match() -> None:
    arr = np.linspace(0.0, 1.0, 100, dtype=np.float32)
    out = _resample_linear(arr, 16_000, 16_000)
    np.testing.assert_array_equal(out, arr)


def test_resample_linear_changes_length_proportionally() -> None:
    arr = np.zeros(1000, dtype=np.float32)
    halved = _resample_linear(arr, 16_000, 8_000)
    assert len(halved) == 500
    doubled = _resample_linear(arr, 8_000, 16_000)
    assert len(doubled) == 2000
