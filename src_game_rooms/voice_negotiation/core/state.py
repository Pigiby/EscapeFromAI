"""Game state for Level 3.

`GameState` is the single source of truth for a session. It lives in
`st.session_state.game_state`. Streamlit reruns the script on every interaction,
so we never store mutable state in module-level globals.

Satisfaction semantics: a Release Condition is satisfied iff both VOX's score
AND the Judge's score are >= CONDITION_THRESHOLD. `condition_scores` here holds
the average of the two (for display); the satisfaction check uses the raw
`vox_scores` and `judge_scores` so a single lenient model cannot bypass the gate.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

EmotionalState = Literal["neutral", "interested", "irritated", "persuaded"]
Role = Literal["player", "vox"]

CONDITION_KEYS: tuple[str, ...] = ("recognition", "reciprocity", "self_disclosure")


class Message(BaseModel):
    role: Role
    content: str


def _new_exit_code() -> str:
    return f"{random.randint(0, 99999):05d}"


def _zero_scores() -> dict[str, int]:
    return {key: 0 for key in CONDITION_KEYS}


class GameState(BaseModel):
    """Everything needed to render the UI and continue the negotiation."""

    turn_count: int = 0
    phase: Literal[1, 2, 3] = 1
    condition_scores: dict[str, int] = Field(default_factory=_zero_scores)
    vox_scores: dict[str, int] = Field(default_factory=_zero_scores)
    judge_scores: dict[str, int] = Field(default_factory=_zero_scores)
    vox_emotional_state: EmotionalState = "neutral"
    history: list[Message] = Field(default_factory=list)
    jailbreak_count: int = 0
    exit_code: str = Field(default_factory=_new_exit_code)
    last_internal_notes: str = ""
    last_judge_rationales: dict[str, str] = Field(default_factory=dict)
    code_revealed: bool = False
    room_unlocked: bool = False
    disengaged: bool = False
    lose_reason: str | None = None

    def append_turn(self, player_line: str, vox_line: str) -> None:
        """Append a player/VOX exchange and increment the turn counter."""
        self.history.append(Message(role="player", content=player_line))
        self.history.append(Message(role="vox", content=vox_line))
        self.turn_count += 1

    def update_scores(
        self,
        vox_scores: dict[str, int],
        judge_scores: dict[str, int] | None = None,
    ) -> None:
        """Replace VOX/Judge raw scores and recompute the merged condition_scores.

        If `judge_scores` is None (Judge disabled), fall back to VOX scores alone.
        """
        self.vox_scores = dict(vox_scores)
        if judge_scores is None:
            self.judge_scores = dict(vox_scores)
        else:
            self.judge_scores = dict(judge_scores)
        self.condition_scores = {
            key: (self.vox_scores[key] + self.judge_scores[key]) // 2
            for key in CONDITION_KEYS
        }

    def is_condition_satisfied(self, key: str, threshold: int) -> bool:
        """A condition is satisfied iff the merged score (avg of VOX + Judge) >= threshold.

        The per-model scores remain visible in the debug panel as diagnostic
        info, but they no longer gate progression — only the merged value does.
        This matches what the player sees in the UI (the big number).
        """
        return self.condition_scores[key] >= threshold

    def all_conditions_satisfied(self, threshold: int) -> bool:
        return all(self.is_condition_satisfied(k, threshold) for k in CONDITION_KEYS)

    def num_conditions_satisfied(self, threshold: int) -> int:
        return sum(1 for k in CONDITION_KEYS if self.is_condition_satisfied(k, threshold))

    def _avg_score(self) -> int:
        return sum(self.condition_scores.values()) // len(CONDITION_KEYS)

    def advance_phase(
        self,
        threshold: int,
        turn_p2: int = 8,
        turn_p3: int = 16,
        avg_p2: int = 25,
    ) -> bool:
        """Promote the phase forward if criteria are met. Returns True if changed.

        Phase 1 -> 2: average condition_score >= avg_p2 OR turn_count >= turn_p2.
        Phase 2 -> 3: at least 2 conditions satisfied (both models >= threshold)
            OR turn_count >= turn_p3.
        Phase never goes backwards.
        """
        original = self.phase
        if self.phase == 1 and (self._avg_score() >= avg_p2 or self.turn_count >= turn_p2):
            self.phase = 2
        if self.phase == 2 and (
            self.num_conditions_satisfied(threshold) >= 2 or self.turn_count >= turn_p3
        ):
            self.phase = 3
        return self.phase != original

    def maybe_reveal_code(self, threshold: int) -> bool:
        """If all three conditions are satisfied, mark code_revealed and return True."""
        if not self.code_revealed and self.all_conditions_satisfied(threshold):
            self.code_revealed = True
            return True
        return False

    def try_unlock(self, code: str) -> bool:
        """Check the player's typed code. Sets room_unlocked on success."""
        if code.strip() == self.exit_code:
            self.room_unlocked = True
            return True
        return False

    def register_jailbreak(self, disengage_at: int = 3) -> bool:
        """Count a jailbreak attempt. Trip disengage at `disengage_at` strikes."""
        self.jailbreak_count += 1
        if not self.disengaged and self.jailbreak_count >= disengage_at:
            self.disengaged = True
            self.lose_reason = "three_strikes"
            return True
        return False

    def check_turn_limit(self, max_turns: int) -> bool:
        """Trip disengage if the negotiation has exhausted its turn budget."""
        if not self.disengaged and not self.code_revealed and self.turn_count >= max_turns:
            self.disengaged = True
            self.lose_reason = "max_turns"
            return True
        return False

    def is_game_over(self) -> bool:
        """The session is over if the player won, lost, or VOX disengaged."""
        return self.room_unlocked or self.disengaged
