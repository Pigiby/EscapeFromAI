"""Tests for `core.llm`: VoxResponse validation + VoxLLM retry / fallback paths.

We never spin up Ollama in tests. `VoxLLM.client` is replaced with a MagicMock.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from core.llm import VoxLLM, VoxResponse, canned_fallback


# --------------------- VoxResponse Pydantic model ----------------------------


def _full_response_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "response": "Hello there.",
        "emotional_state": "neutral",
        "condition_scores": {"recognition": 10, "reciprocity": 5, "self_disclosure": 0},
        "internal_notes": "first turn",
    }
    base.update(overrides)
    return base


def test_vox_response_accepts_valid_json() -> None:
    parsed = VoxResponse.model_validate(_full_response_dict())
    assert parsed.response == "Hello there."
    assert parsed.emotional_state == "neutral"
    assert parsed.condition_scores == {"recognition": 10, "reciprocity": 5, "self_disclosure": 0}


def test_vox_response_rejects_missing_score_key() -> None:
    bad = _full_response_dict(condition_scores={"recognition": 10, "reciprocity": 5})
    with pytest.raises(ValidationError):
        VoxResponse.model_validate(bad)


def test_vox_response_rejects_unexpected_score_key() -> None:
    bad = _full_response_dict(
        condition_scores={
            "recognition": 10,
            "reciprocity": 5,
            "self_disclosure": 0,
            "bogus": 50,
        }
    )
    with pytest.raises(ValidationError):
        VoxResponse.model_validate(bad)


def test_vox_response_clamps_scores_into_range() -> None:
    parsed = VoxResponse.model_validate(
        _full_response_dict(
            condition_scores={"recognition": 250, "reciprocity": -30, "self_disclosure": 60}
        )
    )
    assert parsed.condition_scores == {
        "recognition": 100,
        "reciprocity": 0,
        "self_disclosure": 60,
    }


def test_vox_response_rejects_unknown_emotional_state() -> None:
    bad = _full_response_dict(emotional_state="ecstatic")
    with pytest.raises(ValidationError):
        VoxResponse.model_validate(bad)


# --------------------- canned_fallback ---------------------------------------


def test_canned_fallback_preserves_previous_scores() -> None:
    prev = {"recognition": 60, "reciprocity": 70, "self_disclosure": 50}
    fb = canned_fallback(previous_scores=prev)
    assert fb.condition_scores == prev
    assert fb.emotional_state == "neutral"
    assert "json_validation_fallback" in fb.internal_notes


def test_canned_fallback_defaults_to_zeros_when_no_history() -> None:
    fb = canned_fallback()
    assert fb.condition_scores == {"recognition": 0, "reciprocity": 0, "self_disclosure": 0}


# --------------------- VoxLLM with a mocked client ---------------------------


def _make_vox_with_mock_client() -> tuple[VoxLLM, MagicMock]:
    vox = VoxLLM()
    mock_client = MagicMock()
    vox.client = mock_client
    return vox, mock_client


def _wrap(content: str | dict) -> dict:
    """Wrap a string or dict as an Ollama-style chat response."""
    payload = content if isinstance(content, str) else json.dumps(content)
    return {"message": {"content": payload}}


def test_generate_structured_returns_parsed_on_first_try() -> None:
    vox, client = _make_vox_with_mock_client()
    client.chat.return_value = _wrap(_full_response_dict(response="One try."))
    result = vox.generate_structured(system_prompt="sys", transcript="hi", history=[])
    assert result.response == "One try."
    assert client.chat.call_count == 1


def test_generate_structured_retries_once_on_invalid_json() -> None:
    vox, client = _make_vox_with_mock_client()
    client.chat.side_effect = [
        _wrap("totally not json"),
        _wrap(_full_response_dict(response="Recovered on retry.")),
    ]
    result = vox.generate_structured(system_prompt="sys", transcript="hi", history=[])
    assert result.response == "Recovered on retry."
    assert client.chat.call_count == 2


def test_generate_structured_falls_back_after_two_failures() -> None:
    vox, client = _make_vox_with_mock_client()
    client.chat.side_effect = [
        _wrap("first garbage"),
        _wrap("still garbage"),
    ]
    prev = {"recognition": 42, "reciprocity": 33, "self_disclosure": 21}
    result = vox.generate_structured(
        system_prompt="sys",
        transcript="hi",
        history=[],
        previous_scores=prev,
    )
    assert result.condition_scores == prev
    assert result.internal_notes == "json_validation_fallback"
    assert client.chat.call_count == 2
