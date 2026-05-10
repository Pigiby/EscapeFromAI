"""Speech-to-text via mlx-whisper, with silero-vad silence trimming.

Both models are loaded once per Streamlit session via `@st.cache_resource`
factories (see `get_stt`). Call sites should always go through the factory,
never instantiate `WhisperSTT` directly, so we don't reload the weights on
every Streamlit rerun.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import streamlit as st

from core.audio_utils import decode_audio_blob, trim_silence_with_vad

DEFAULT_MODEL_REPO = "mlx-community/whisper-large-v3-turbo"
DEFAULT_LANGUAGE = "en"

logger = logging.getLogger(__name__)


class WhisperSTT:
    """mlx-whisper wrapper. Stateless except for the bound model repo + language."""

    def __init__(
        self,
        model_repo: str = DEFAULT_MODEL_REPO,
        language: str = DEFAULT_LANGUAGE,
        vad_model: Any | None = None,
    ) -> None:
        self.model_repo = model_repo
        self.language = language
        self.vad_model = vad_model

    def transcribe(self, audio_bytes: bytes) -> str:
        """Decode a raw audio blob, trim silence, run Whisper, return the text.

        Returns an empty string if no speech is detected or transcription fails.
        """
        try:
            audio = decode_audio_blob(audio_bytes)
        except ValueError:
            logger.warning("Empty or undecodable audio blob")
            return ""
        if self.vad_model is not None:
            audio = trim_silence_with_vad(audio, self.vad_model)
        if audio.size == 0:
            return ""
        return self._transcribe_array(audio)

    def _transcribe_array(self, audio: np.ndarray) -> str:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model_repo,
            language=self.language,
        )
        text = (result.get("text") or "").strip()
        logger.info("STT: %d samples -> %d chars", audio.size, len(text))
        return text


@st.cache_resource(show_spinner="Loading silero-vad...")
def get_vad_model() -> Any:
    """Load silero-vad once per session."""
    from silero_vad import load_silero_vad

    return load_silero_vad()


@st.cache_resource(show_spinner="Loading Whisper...")
def get_stt(model_repo: str = DEFAULT_MODEL_REPO, language: str = DEFAULT_LANGUAGE) -> WhisperSTT:
    """Get the cached WhisperSTT instance (with VAD attached)."""
    vad = get_vad_model()
    return WhisperSTT(model_repo=model_repo, language=language, vad_model=vad)
