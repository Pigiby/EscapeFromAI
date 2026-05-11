"""Judge LLM: an impartial classifier that scores the three Release Conditions.

Runs in parallel with VOX (see `app.py`). The Judge sees the full conversation
history up to and including the latest player turn, and outputs:

    {
      "condition_scores": {"recognition": int, "reciprocity": int, "self_disclosure": int},
      "rationales": {"recognition": str, "reciprocity": str, "self_disclosure": str}
    }

The Judge is small (3B) and cold (temperature 0.2) by design.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import streamlit as st
from pydantic import BaseModel, Field, ValidationError, field_validator

from core.state import CONDITION_KEYS, Message

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b-instruct"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT = 60

logger = logging.getLogger(__name__)


class JudgeResponse(BaseModel):
    """Strict schema for the Judge's per-turn output. Mirrors prompts/judge_system.md."""

    condition_scores: dict[str, int]
    rationales: dict[str, str] = Field(default_factory=dict)

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


def load_judge_system_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


def neutral_fallback(previous_scores: dict[str, int] | None = None) -> JudgeResponse:
    """Returned when the Judge fails to produce valid JSON twice.

    Preserves the previous Judge scores so a transient parse failure does not
    drop the player back to 0.
    """
    scores = previous_scores or {k: 0 for k in CONDITION_KEYS}
    return JudgeResponse(
        condition_scores=scores,
        rationales={k: "judge_validation_fallback" for k in CONDITION_KEYS},
    )


class JudgeLLM:
    """Thin Ollama wrapper for the Judge model."""

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

    def evaluate(
        self,
        system_prompt: str,
        transcript: str,
        history: list[Message],
        previous_scores: dict[str, int] | None = None,
    ) -> JudgeResponse:
        """Score the conversation cumulatively, with one retry on parse failure."""
        conversation_text = _format_conversation(history, latest_player_line=transcript)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text},
        ]
        first = self._chat(messages)
        parsed, error = self._try_parse(first)
        if parsed is not None:
            return parsed

        logger.warning("Judge JSON invalid: %s; retrying", error)
        retry_messages = messages + [
            {"role": "assistant", "content": first},
            {
                "role": "user",
                "content": (
                    "Your previous reply did not match the required JSON schema. "
                    f"Error: {error}. "
                    "Reply ONLY with valid JSON matching the schema, nothing else."
                ),
            },
        ]
        second = self._chat(retry_messages)
        parsed, error = self._try_parse(second)
        if parsed is not None:
            return parsed
        logger.error("Judge JSON invalid on retry: %s; using fallback", error)
        return neutral_fallback(previous_scores)

    def _chat(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature, "num_predict": 256},
            format="json",
            keep_alive="30m",
        )
        content = response["message"]["content"]
        logger.info("Judge: %d-char reply", len(content))
        return content

    @staticmethod
    def _try_parse(raw: str) -> tuple[JudgeResponse | None, str]:
        try:
            return JudgeResponse.model_validate_json(raw), ""
        except ValidationError as e:
            issues = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err.get("loc", ()))
                issues.append(f"{loc}: {err.get('msg', 'invalid')}")
            return None, "; ".join(issues) or "validation failed"
        except json.JSONDecodeError as e:
            return None, f"not valid JSON: {e.msg} at pos {e.pos}"


def _format_conversation(history: list[Message], latest_player_line: str) -> str:
    """Render the conversation as plain text for the Judge's single-user-message input."""
    from core.llm import _trim_history  # share the same window policy as VOX

    recent = _trim_history(history)
    lines: list[str] = []
    for msg in recent:
        speaker = "Player" if msg.role == "player" else "VOX"
        lines.append(f"{speaker}: {msg.content}")
    lines.append(f"Player: {latest_player_line}")
    body = "\n".join(lines)
    return (
        "Score the player's contributions in the following conversation against the three "
        "criteria from the system prompt. Consider the cumulative context, not only the "
        "most recent line. Reply with the JSON object only.\n\n"
        f"{body}"
    )


@st.cache_resource(show_spinner="Connecting to Judge...")
def get_judge_llm(
    host: str = DEFAULT_OLLAMA_HOST,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: int = DEFAULT_TIMEOUT,
) -> JudgeLLM:
    return JudgeLLM(host=host, model=model, temperature=temperature, timeout=timeout)
