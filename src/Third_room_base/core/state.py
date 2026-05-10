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
        """A condition is satisfied iff both VOX and Judge agree it is."""
        return self.vox_scores[key] >= threshold and self.judge_scores[key] >= threshold

    def all_conditions_satisfied(self, threshold: int) -> bool:
        return all(self.is_condition_satisfied(k, threshold) for k in CONDITION_KEYS)

    def num_conditions_satisfied(self, threshold: int) -> int:
        return sum(1 for k in CONDITION_KEYS if self.is_condition_satisfied(k, threshold))
