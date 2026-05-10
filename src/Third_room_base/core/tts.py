"""Text-to-speech via Piper.

Uses the `piper-tts` Python package (`from piper import PiperVoice`). The
synthesized audio is returned as in-memory WAV bytes for Streamlit's
`st.audio(..., autoplay=True)`.

The voice model is loaded once per session via `@st.cache_resource`.
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

logger = logging.getLogger(__name__)


class PiperTTS:
    """Wrapper around a loaded PiperVoice. `synthesize` returns WAV bytes."""

    def __init__(self, voice: Any, length_scale: float = DEFAULT_LENGTH_SCALE) -> None:
        self._voice = voice
        self.length_scale = length_scale

    def synthesize(self, text: str) -> bytes:
        """Synthesize `text` to in-memory WAV bytes (16-bit PCM, model SR)."""
        if not text.strip():
            return b""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            self._voice.synthesize(text, wav_file, length_scale=self.length_scale)
        data = buf.getvalue()
        logger.info("TTS: %d chars -> %d bytes wav", len(text), len(data))
        return data


@st.cache_resource(show_spinner="Loading VOX voice...")
def get_tts(voice_path: str = DEFAULT_VOICE_PATH, length_scale: float = DEFAULT_LENGTH_SCALE) -> PiperTTS:
    """Load the Piper voice once and wrap it in PiperTTS."""
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
