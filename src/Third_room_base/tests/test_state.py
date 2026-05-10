"""Tests for `core.state.GameState`."""
from __future__ import annotations

import re

from core.state import CONDITION_KEYS, GameState, Message


def test_default_construction() -> None:
    gs = GameState()
    assert gs.turn_count == 0
    assert gs.phase == 1
    assert gs.vox_emotional_state == "neutral"
    assert gs.history == []
    assert gs.jailbreak_count == 0
    assert gs.code_revealed is False
    assert set(gs.condition_scores.keys()) == set(CONDITION_KEYS)
    assert all(v == 0 for v in gs.condition_scores.values())


def test_exit_code_is_five_digits() -> None:
    for _ in range(20):
        gs = GameState()
        assert re.fullmatch(r"\d{5}", gs.exit_code), f"bad exit_code={gs.exit_code}"


def test_append_turn_extends_history_and_counts() -> None:
    gs = GameState()
    gs.append_turn("hello", "another one")
    assert gs.turn_count == 1
    assert gs.history == [
        Message(role="player", content="hello"),
        Message(role="vox", content="another one"),
    ]
    gs.append_turn("more", "indeed")
    assert gs.turn_count == 2
    assert len(gs.history) == 4


def test_update_scores_with_both_models_averages() -> None:
    gs = GameState()
    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 40, "self_disclosure": 60},
        judge_scores={"recognition": 60, "reciprocity": 50, "self_disclosure": 70},
    )
    assert gs.vox_scores == {"recognition": 80, "reciprocity": 40, "self_disclosure": 60}
    assert gs.judge_scores == {"recognition": 60, "reciprocity": 50, "self_disclosure": 70}
    assert gs.condition_scores == {"recognition": 70, "reciprocity": 45, "self_disclosure": 65}


def test_update_scores_without_judge_falls_back_to_vox() -> None:
    gs = GameState()
    vox = {"recognition": 80, "reciprocity": 40, "self_disclosure": 60}
    gs.update_scores(vox_scores=vox)
    assert gs.vox_scores == vox
    assert gs.judge_scores == vox
    assert gs.condition_scores == vox


def test_is_condition_satisfied_requires_both_models_to_agree() -> None:
    gs = GameState()
    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 40, "self_disclosure": 80},
        judge_scores={"recognition": 78, "reciprocity": 90, "self_disclosure": 60},
    )
    # recognition: both ≥ 75 -> satisfied
    assert gs.is_condition_satisfied("recognition", 75) is True
    # reciprocity: VOX 40 < 75 -> not satisfied even though Judge is 90
    assert gs.is_condition_satisfied("reciprocity", 75) is False
    # self_disclosure: Judge 60 < 75 -> not satisfied even though VOX is 80
    assert gs.is_condition_satisfied("self_disclosure", 75) is False
    assert gs.num_conditions_satisfied(75) == 1
    assert gs.all_conditions_satisfied(75) is False


def test_all_conditions_satisfied_true_when_all_three_agree() -> None:
    gs = GameState()
    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 80},
        judge_scores={"recognition": 75, "reciprocity": 90, "self_disclosure": 76},
    )
    assert gs.all_conditions_satisfied(75) is True
    assert gs.num_conditions_satisfied(75) == 3
