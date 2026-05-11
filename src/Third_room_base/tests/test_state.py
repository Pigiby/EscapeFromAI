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


def test_advance_phase_via_avg_score() -> None:
    gs = GameState()
    # Avg score is 30 (well above default 25), turn_count is 0 -> phase 1 -> 2
    gs.update_scores(vox_scores={"recognition": 30, "reciprocity": 30, "self_disclosure": 30})
    assert gs.advance_phase(threshold=75) is True
    assert gs.phase == 2


def test_advance_phase_via_turn_count() -> None:
    gs = GameState()
    gs.turn_count = 8  # at the threshold even with zero scores -> phase 1 -> 2
    assert gs.advance_phase(threshold=75) is True
    assert gs.phase == 2


def test_advance_phase_to_3_when_two_conditions_satisfied() -> None:
    gs = GameState()
    gs.phase = 2
    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 10},
        judge_scores={"recognition": 90, "reciprocity": 85, "self_disclosure": 10},
    )
    assert gs.advance_phase(threshold=75) is True
    assert gs.phase == 3


def test_advance_phase_does_not_regress() -> None:
    gs = GameState()
    gs.phase = 3
    # No criteria met for 3 but we shouldn't go back
    assert gs.advance_phase(threshold=75) is False
    assert gs.phase == 3


def test_maybe_reveal_code_only_when_all_three_satisfied() -> None:
    gs = GameState()
    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 70},
        judge_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 80},
    )
    # self_disclosure VOX side is 70 < 75 -> not satisfied
    assert gs.maybe_reveal_code(threshold=75) is False
    assert gs.code_revealed is False

    gs.update_scores(
        vox_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 80},
        judge_scores={"recognition": 80, "reciprocity": 80, "self_disclosure": 80},
    )
    assert gs.maybe_reveal_code(threshold=75) is True
    assert gs.code_revealed is True
    # idempotent: second call returns False (already revealed)
    assert gs.maybe_reveal_code(threshold=75) is False


def test_try_unlock_matches_exit_code() -> None:
    gs = GameState()
    gs.exit_code = "12345"
    assert gs.try_unlock("99999") is False
    assert gs.room_unlocked is False
    assert gs.try_unlock(" 12345 ") is True  # whitespace tolerated
    assert gs.room_unlocked is True


def test_register_jailbreak_trips_disengage_at_three() -> None:
    gs = GameState()
    assert gs.register_jailbreak() is False
    assert gs.register_jailbreak() is False
    assert gs.disengaged is False
    assert gs.register_jailbreak() is True  # third strike
    assert gs.disengaged is True
    assert gs.lose_reason == "three_strikes"
    assert gs.jailbreak_count == 3
    # further strikes don't double-trigger
    assert gs.register_jailbreak() is False
    assert gs.lose_reason == "three_strikes"


def test_check_turn_limit_disengages_when_exhausted() -> None:
    gs = GameState()
    gs.turn_count = 29
    assert gs.check_turn_limit(max_turns=30) is False
    gs.turn_count = 30
    assert gs.check_turn_limit(max_turns=30) is True
    assert gs.disengaged is True
    assert gs.lose_reason == "max_turns"


def test_check_turn_limit_no_op_if_code_already_revealed() -> None:
    gs = GameState()
    gs.code_revealed = True
    gs.turn_count = 99
    assert gs.check_turn_limit(max_turns=30) is False
    assert gs.disengaged is False


def test_is_game_over() -> None:
    gs = GameState()
    assert gs.is_game_over() is False
    gs.disengaged = True
    assert gs.is_game_over() is True
    gs2 = GameState()
    gs2.room_unlocked = True
    assert gs2.is_game_over() is True
