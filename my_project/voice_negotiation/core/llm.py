"""VOX LLM wrapper around Ollama, with Pydantic-validated JSON output.

Public surface:
    - VoxResponse: the Pydantic model VOX must emit each turn
    - VoxLLM.generate_structured(...) -> VoxResponse: validated, with 1 retry
    - VoxLLM.generate_raw(...) -> str: escape hatch returning the raw JSON

History is mapped to the Ollama chat format:
    Player -> "user"
    VOX    -> "assistant"

If VOX returns malformed JSON twice in a row, `generate_structured` returns a
canned fallback that preserves the previous condition scores (so a parse
hiccup doesn't penalize the player).
"""
from __future__ import annotations

import json
import logging
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .state import CONDITION_KEYS, Message

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b-instruct"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 300

logger = logging.getLogger(__name__)


class VoxResponse(BaseModel):
    """Strict schema for VOX's per-turn output. Mirrors prompts/vox_system.md."""

    response: str = Field(min_length=1)
    emotional_state: Literal["neutral", "interested", "irritated", "persuaded"]
    condition_scores: dict[str, int]
    internal_notes: str = ""
    jailbreak_attempted: bool = False

    @field_validator("condition_scores")
    @classmethod
    def _validate_scores(cls, v: dict[str, int]) -> dict[str, int]:
        missing = set(CONDITION_KEYS) - set(v.keys())
        if missing:
            raise ValueError(f"missing condition keys: {sorted(missing)}")
        extra = set(v.keys()) - set(CONDITION_KEYS)
        if extra:
            raise ValueError(f"unexpected condition keys: {sorted(extra)}")
        clamped: dict[str, int] = {}
        for key, value in v.items():
            try:
                ivalue = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"score for {key} not an integer: {value!r}") from exc
            clamped[key] = max(0, min(100, ivalue))
        return clamped


def load_vox_system_prompt(
    prompt_path: Path,
    exit_code: str,
    condition_threshold: int,
) -> str:
    """Read the VOX prompt template and substitute `{exit_code}` and `{condition_threshold}`."""
    template = prompt_path.read_text(encoding="utf-8")
    return (
        template
        .replace("{exit_code}", exit_code)
        .replace("{condition_threshold}", str(condition_threshold))
    )


def canned_fallback(previous_scores: dict[str, int] | None = None) -> VoxResponse:
    """A safe response when VOX's JSON cannot be parsed twice in a row.

    Preserves the previous condition scores so a parse failure does not penalize
    the player.
    """
    scores = previous_scores or {k: 0 for k in CONDITION_KEYS}
    return VoxResponse(
        response="My apologies. I lost the thread for a moment. Could you say that again?",
        emotional_state="neutral",
        condition_scores=scores,
        internal_notes="json_validation_fallback",
    )


class VoxLLM:
    """Thin Ollama wrapper. Stateless beyond model + connection configuration."""

    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        import ollama

        self.model = model
        self.temperature = temperature
        self.client = ollama.Client(host=host, timeout=timeout)

    def generate_raw(
        self,
        system_prompt: str,
        transcript: str,
        history: list[Message],
    ) -> str:
        """Single Ollama call. Returns the raw assistant content."""
        messages = self._build_messages(system_prompt, transcript, history)
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature, "num_predict": 256},
            format="json",
            keep_alive="30m",
        )
        content = response["message"]["content"]
        logger.info("VOX: %d-char reply (%d-message context)", len(content), len(messages))
        return content

    def generate_structured(
        self,
        system_prompt: str,
        transcript: str,
        history: list[Message],
        previous_scores: dict[str, int] | None = None,
    ) -> VoxResponse:
        """Call VOX, validate with Pydantic, retry once, fall back if needed."""
        messages = self._build_messages(system_prompt, transcript, history)
        first = self._chat(messages)
        parsed, error = self._try_parse(first)
        if parsed is not None:
            return parsed

        logger.warning("VOX JSON invalid: %s; retrying with correction prompt", error)
        retry_messages = messages + [
            {"role": "assistant", "content": first},
            {
                "role": "user",
                "content": (
                    "Your previous reply did not match the required JSON schema. "
                    f"Error: {error}. "
                    "Reply ONLY with valid JSON matching the documented schema, "
                    "nothing else. Same response, fixed format."
                ),
            },
        ]
        second = self._chat(retry_messages)
        parsed, error = self._try_parse(second)
        if parsed is not None:
            return parsed

        logger.error("VOX JSON invalid on retry: %s; using canned fallback", error)
        return canned_fallback(previous_scores)

    def _chat(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature, "num_predict": 256},
            format="json",
            keep_alive="30m",
        )
        content = response["message"]["content"]
        logger.info("VOX: %d-char reply (%d-message context)", len(content), len(messages))
        return content

    @staticmethod
    def _try_parse(raw: str) -> tuple[VoxResponse | None, str]:
        try:
            return VoxResponse.model_validate_json(raw), ""
        except ValidationError as e:
            return None, _summarize_validation_error(e)
        except json.JSONDecodeError as e:
            return None, f"not valid JSON: {e.msg} at pos {e.pos}"

    @staticmethod
    def _build_messages(
        system_prompt: str,
        transcript: str,
        history: list[Message],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        recent = _trim_history(history)
        for msg in recent:
            role = "user" if msg.role == "player" else "assistant"
            messages.append({"role": role, "content": msg.content})
        messages.append({"role": "user", "content": transcript})
        return messages


def _summarize_validation_error(e: ValidationError) -> str:
    issues = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        issues.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(issues) or "validation failed"


def _trim_history(history: list[Message]) -> list[Message]:
    """Keep only the most recent turns to bound prompt size.

    Long history makes prompt processing slow on Apple Silicon for 7B models.
    The system prompt re-establishes VOX each turn, so a short sliding window
    is sufficient for conversational coherence.
    """
    import os
    keep = int(os.getenv("MAX_HISTORY_MESSAGES", "6"))
    if keep <= 0 or len(history) <= keep:
        return list(history)
    return list(history[-keep:])


@cache
def get_vox_llm(
    host: str = DEFAULT_OLLAMA_HOST,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: int = DEFAULT_TIMEOUT,
) -> VoxLLM:
    return VoxLLM(host=host, model=model, temperature=temperature, timeout=timeout)
