"""Audio I/O helpers for converting raw browser/uploaded audio blobs into the
numpy arrays expected by Whisper, silero-vad, and Piper.

All audio inside the pipeline is normalized to: 16 kHz, mono, float32 in [-1, 1].
"""
from __future__ import annotations

import io
import logging
import subprocess

import numpy as np
import soundfile as sf

TARGET_SAMPLE_RATE = 16_000

logger = logging.getLogger(__name__)


def decode_audio_blob(raw: bytes) -> np.ndarray:
    """Decode a raw audio blob (WAV/OGG/M4A/MP3/WebM/Opus/...) to 16 kHz mono float32.

    Tries libsndfile first (fast, handles WAV/OGG/FLAC). Falls back to a
    direct ffmpeg subprocess for everything else (WebM-Opus from browser
    MediaRecorder, MP3, M4A from macOS Voice Memos, etc.).

    Requires `ffmpeg` on PATH for the fallback path.

    Args:
        raw: Raw audio bytes (whatever format the browser/uploader produced).

    Returns:
        1-D numpy array, float32, sample rate 16 kHz.

    Raises:
        ValueError: If the blob is empty or cannot be decoded.
    """
    if not raw:
        raise ValueError("Empty audio blob")
    try:
        with io.BytesIO(raw) as buf:
            data, sample_rate = sf.read(buf, dtype="float32", always_2d=False)
        return _to_float32_mono_16k(data, sample_rate)
    except Exception as sf_err:
        logger.info("soundfile cannot decode (%s); piping through ffmpeg", sf_err)
        try:
            return _decode_via_ffmpeg(raw)
        except (FileNotFoundError, subprocess.CalledProcessError) as ff_err:
            raise ValueError(
                f"Audio decode failed. soundfile error: {sf_err}; ffmpeg error: {ff_err}. "
                "Install ffmpeg (`brew install ffmpeg`) if it's missing."
            ) from ff_err


def _decode_via_ffmpeg(raw: bytes) -> np.ndarray:
    """Pipe arbitrary audio through ffmpeg to 16 kHz mono float32 PCM."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-ac", "1",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-f", "f32le",
            "pipe:1",
        ],
        input=raw,
        capture_output=True,
        check=True,
    )
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if audio.size == 0:
        raise ValueError("ffmpeg produced empty audio")
    return audio


def _to_float32_mono_16k(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Mix to mono, resample to 16 kHz, ensure float32."""
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    samples = samples.astype(np.float32, copy=False)
    if sample_rate != TARGET_SAMPLE_RATE:
        samples = _resample_linear(samples, sample_rate, TARGET_SAMPLE_RATE)
    return samples


def _resample_linear(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Simple linear resampling. Good enough for speech (Whisper is robust).

    We avoid pulling in librosa here for the hot path; librosa is still in
    requirements.txt for slicing/diagnostic use.
    """
    if src_sr == dst_sr:
        return samples
    duration = samples.shape[0] / src_sr
    new_length = int(round(duration * dst_sr))
    if new_length <= 1:
        return np.zeros(0, dtype=np.float32)
    src_indices = np.linspace(0.0, samples.shape[0] - 1, num=new_length, dtype=np.float64)
    floor = np.floor(src_indices).astype(np.int64)
    ceil = np.minimum(floor + 1, samples.shape[0] - 1)
    frac = (src_indices - floor).astype(np.float32)
    return (samples[floor] * (1.0 - frac) + samples[ceil] * frac).astype(np.float32)


def trim_silence_with_vad(audio: np.ndarray, vad_model) -> np.ndarray:
    """Trim leading/trailing silence using silero-vad.

    Detects speech segments and returns the audio cropped from the first speech
    sample to the last. If no speech is detected, returns the input unchanged
    (Whisper will then transcribe an empty result, which we treat as 'silence').

    Args:
        audio: 1-D float32 numpy array at 16 kHz.
        vad_model: A loaded silero-vad model (see `core.stt.get_vad_model`).

    Returns:
        Cropped 1-D float32 array.
    """
    try:
        import torch
        from silero_vad import get_speech_timestamps
    except ImportError as e:
        logger.warning("silero-vad/torch missing, skipping VAD trim: %s", e)
        return audio
    if audio.size == 0:
        return audio
    tensor = torch.from_numpy(audio)
    timestamps = get_speech_timestamps(
        tensor,
        vad_model,
        sampling_rate=TARGET_SAMPLE_RATE,
        return_seconds=False,
    )
    if not timestamps:
        logger.info("VAD found no speech; returning original audio")
        return audio
    start = max(0, timestamps[0]["start"])
    end = min(audio.shape[0], timestamps[-1]["end"])
    return audio[start:end]
