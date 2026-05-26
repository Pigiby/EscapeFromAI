"""Speech-to-text with silero-vad silence trimming.

Backend is selected automatically at runtime:
  - Apple Silicon macOS  →  mlx-whisper  (fast, Metal-accelerated)
  - everything else      →  openai-whisper (CPU, cross-platform)

Both models are loaded once per process via `functools.cache` factories
(see `get_stt`). Call sites should always go through the factory, never
instantiate `WhisperSTT` directly, so we don't reload the weights.
"""
from __future__ import annotations

import logging
import platform
import sys
from functools import cache
from typing import Any

import numpy as np

from .audio_utils import decode_audio_blob, trim_silence_with_vad

# Apple Silicon: use mlx-whisper HuggingFace repo
DEFAULT_MODEL_MLX = "mlx-community/whisper-large-v3-turbo"
# All other platforms: use openai-whisper model name
DEFAULT_MODEL_OPENAI = "large-v3"
DEFAULT_LANGUAGE = "en"

logger = logging.getLogger(__name__)


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


class WhisperSTT:
    """Whisper wrapper that selects the backend based on the current hardware."""

    def __init__(
        self,
        model_repo: str | None = None,
        language: str = DEFAULT_LANGUAGE,
        vad_model: Any | None = None,
    ) -> None:
        self.apple_silicon = _is_apple_silicon()
        if model_repo is None:
            model_repo = DEFAULT_MODEL_MLX if self.apple_silicon else DEFAULT_MODEL_OPENAI
        self.model_repo = model_repo
        self.language = language
        self.vad_model = vad_model
        logger.info(
            "STT backend: %s | model: %s",
            "mlx-whisper" if self.apple_silicon else "openai-whisper",
            self.model_repo,
        )

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
        if self.apple_silicon:
            return self._transcribe_mlx(audio)
        return self._transcribe_openai(audio)

    def _transcribe_mlx(self, audio: np.ndarray) -> str:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model_repo,
            language=self.language,
        )
        text = (result.get("text") or "").strip()
        logger.info("STT (mlx): %d samples -> %d chars", audio.size, len(text))
        return text

    def _transcribe_openai(self, audio: np.ndarray) -> str:
        import whisper

        # openai-whisper caches the loaded model internally; load_model is cheap
        # on repeat calls when the model name hasn't changed.
        model = whisper.load_model(self.model_repo)
        result = model.transcribe(audio, language=self.language)
        text = (result.get("text") or "").strip()
        logger.info("STT (openai-whisper): %d samples -> %d chars", audio.size, len(text))
        return text


@cache
def get_vad_model() -> Any:
    """Load silero-vad once per process."""
    from silero_vad import load_silero_vad

    return load_silero_vad()


@cache
def get_stt(model_repo: str | None = None, language: str = DEFAULT_LANGUAGE) -> WhisperSTT:
    """Get the cached WhisperSTT instance (with VAD attached)."""
    vad = get_vad_model()
    return WhisperSTT(model_repo=model_repo, language=language, vad_model=vad)
