"""Text-to-speech via Piper.

Uses the `piper-tts` Python package (`from piper import PiperVoice`). The
synthesized audio is returned as in-memory WAV bytes for Streamlit's
`st.audio(..., autoplay=True)`.

The voice model is loaded once per session via `@st.cache_resource`.

Each call accepts a `mood` argument that selects a SynthesisConfig profile
from `EMOTION_PROFILES`, so VOX sounds different across emotional states
(flatter when irritated, livelier when interested, warmer when persuaded).
The constructor's `length_scale` is a global multiplier applied on top of
the per-mood pacing, so a user can globally slow down or speed up the voice
without losing the relative emotional spacing.
"""
from __future__ import annotations

import io
import logging
import wave
from pathlib import Path
from typing import Any

import streamlit as st

DEFAULT_VOICE_PATH = "assets/voices/en_US-amy-medium.onnx"
DEFAULT_LENGTH_SCALE = 1.0
DEFAULT_MOOD = "neutral"

EMOTION_PROFILES: dict[str, dict[str, float]] = {
    # length_scale: pacing (1.0 = normal; <1 = faster; >1 = slower)
    # noise_scale: timbral variation (low = flat/monotone, high = expressive)
    # noise_w_scale: rhythmic variation (low = mechanical, high = organic)
    # volume is intentionally omitted: Piper's normalize_audio defaults to True
    # and rescales the output peak to 1.0, which makes per-mood volume changes
    # inaudible. We rely on the three knobs above for differentiation.
    "neutral":    {"length_scale": 1.00, "noise_scale": 0.667, "noise_w_scale": 0.80},
    "interested": {"length_scale": 0.82, "noise_scale": 0.95,  "noise_w_scale": 1.05},
    "irritated":  {"length_scale": 0.85, "noise_scale": 0.20,  "noise_w_scale": 0.40},
    "persuaded":  {"length_scale": 1.22, "noise_scale": 0.85,  "noise_w_scale": 1.10},
}

logger = logging.getLogger(__name__)


class PiperTTS:
    """Wrapper around a loaded PiperVoice. `synthesize` returns WAV bytes."""

    def __init__(self, voice: Any, length_scale: float = DEFAULT_LENGTH_SCALE) -> None:
        self._voice = voice
        self.length_scale = length_scale

    def synthesize(self, text: str, mood: str = DEFAULT_MOOD) -> bytes:
        """Synthesize `text` to in-memory WAV bytes (16-bit PCM, model SR).

        Args:
            text: the line VOX will speak.
            mood: one of the keys in `EMOTION_PROFILES`. Unknown values fall
                back to "neutral".
        """
        if not text.strip():
            return b""
        from piper.config import SynthesisConfig

        profile = EMOTION_PROFILES.get(mood, EMOTION_PROFILES[DEFAULT_MOOD])
        syn_config = SynthesisConfig(
            length_scale=profile["length_scale"] * self.length_scale,
            noise_scale=profile["noise_scale"],
            noise_w_scale=profile["noise_w_scale"],
        )
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=syn_config)
        data = buf.getvalue()
        logger.info("TTS: mood=%s, %d chars -> %d bytes wav", mood, len(text), len(data))
        return data


@st.cache_resource(show_spinner="Loading VOX voice...")
def get_tts(voice_path: str = DEFAULT_VOICE_PATH, length_scale: float = DEFAULT_LENGTH_SCALE) -> PiperTTS:
    """Load the Piper voice once and wrap it in PiperTTS.

    `length_scale` here is the global pacing multiplier applied on top of
    the per-mood profile in `EMOTION_PROFILES`.
    """
    from piper import PiperVoice

    resolved = Path(voice_path)
    if not resolved.is_absolute():
        resolved = Path(__file__).resolve().parent.parent / voice_path
    if not resolved.exists():
        raise FileNotFoundError(
            f"Piper voice not found at {resolved}. "
            f"Download it per README.md step 4 (assets/voices/{resolved.name})."
        )
    voice = PiperVoice.load(str(resolved))
    return PiperTTS(voice=voice, length_scale=length_scale)
