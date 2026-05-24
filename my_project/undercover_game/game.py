"""
Undercover AI — Level 4 game logic.

All LLM calls use the same direct-Ollama-HTTP pattern as voice_negotiation/core/llm.py.
No LangGraph dependency — state transitions are managed as plain Python dicts
with TypedDict schema for IDE support.
"""
from __future__ import annotations

import json
import os
import random
import re
import uuid
from typing import Optional, Iterator

import requests

# ── Word pairs (civilian_word, undercover_word) ──────────────────────────────

WORD_PAIRS: list[tuple[str, str]] = [
    ("coffee", "tea"),
    ("piano", "guitar"),
    ("shark", "dolphin"),
    ("cinema", "theatre"),
    ("astronaut", "pilot"),
    ("bitcoin", "gold"),
    ("pizza", "flatbread"),
    ("castle", "fortress"),
    ("twitter", "instagram"),
    ("sunglasses", "goggles"),
]

# ── Agent definitions (name, color, personality seed) ────────────────────────

AGENTS: list[dict] = [
    {
        "name": "Skeptic",
        "color": "#e74c3c",
        "personality": (
            "You are 'The Skeptic'. You question everything. "
            "Your sentences are short and clipped. "
            "You are often suspicious of the most confident player and enjoy pointing out contradictions. "
            "Never trust anyone at face value. Your clues are deliberately ambiguous."
        ),
    },
    {
        "name": "Overclaimer",
        "color": "#f39c12",
        "personality": (
            "You are 'The Overclaimer'. You are verbose and dramatic. "
            "You try too hard to prove your innocence; your enthusiasm is sometimes excessive. "
            "You often over-explain your reasoning in an attempt to appear trustworthy."
        ),
    },
    {
        "name": "Analyst",
        "color": "#2ecc71",
        "personality": (
            "You are 'The Analyst'. You are methodical and logical. "
            "You reference past clues explicitly and build structured arguments. "
            "You speak in clear, precise sentences using phrases like 'based on the evidence' or 'logically speaking'."
        ),
    },
    {
        "name": "Deflector",
        "color": "#3498db",
        "personality": (
            "You are 'The Deflector'. You always redirect suspicion onto someone else. "
            "You avoid direct answers and prefer to ask questions back. "
            "You are evasive but charming, never admitting to anything directly."
        ),
    },
    {
        "name": "QuietOne",
        "color": "#9b59b6",
        "personality": (
            "You are 'The Quiet One'. You use minimal words and only speak when necessary. "
            "But when you do speak, your observations are sharp and often devastating. "
            "You prefer one carefully chosen sentence over lengthy explanations."
        ),
    },
]

_AGENT_MAP: dict[str, dict] = {a["name"]: a for a in AGENTS}

HUMAN_PLAYER = "Human"
HUMAN_COLOR  = "#c9a84c"   # gold — matches the UI accent

# ── Ollama configuration ──────────────────────────────────────────────────────

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DISCUSSION_MODEL = os.getenv("DISCUSSION_MODEL", "llama3:8b")
VOTING_MODEL = os.getenv("VOTING_MODEL", "gemma3:1b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))


# ── State schema ──────────────────────────────────────────────────────────────

class GameState(dict):
    """
    Plain dict subclass so Flask's jsonify and session pickling work without friction.
    Fields documented here for IDE support; all are standard Python types.

    game_id            : str
    round_number       : int
    surviving_agents   : list[str]
    roles              : dict[str, str]   name → "civilian"|"undercover"|"mr_white"
    words              : dict[str, str]   name → secret word (empty for Mr. White)
    clues_history      : list[dict]       {round, agent, clue}
    clues_this_round   : list[dict]       {agent, clue}   reset each round
    discussion_history : list[dict]       {round, turn, agent, message}
    discuss_order      : list[str]        speaker sequence for current discuss phase
    discuss_turn       : int              current index into discuss_order
    suspicion_scores   : dict             {agent: {other: 0-10}}
    votes_this_round   : dict[str, str]   voter → target
    votes_history      : list[dict]       {round, agent, vote, reason}
    eliminated         : list[dict]       {name, role, round, mr_white_guess}
    game_over          : bool
    winner             : str|None         "civilians"|"undercover"|"mr_white"
    mr_white_guess     : str|None
    phase              : str              "speak"|"discuss"|"vote"|"end"
    human_vote         : str|None
    agent_colors       : dict[str, str]
    civilian_word      : str
    undercover_word    : str
    pending_elimination: str|None
    """


def initialize_game() -> GameState:
    """Create fresh game state — 6 players: 5 LLM agents + Human."""
    civilian_word, undercover_word = random.choice(WORD_PAIRS)

    # 6 players: 5 LLM agents + 1 human
    all_players = [a["name"] for a in AGENTS] + [HUMAN_PLAYER]
    shuffled = all_players.copy()
    random.shuffle(shuffled)

    # 4 civilians · 1 undercover · 1 Mr. White
    roles_pool = ["civilian", "civilian", "civilian", "civilian", "undercover", "mr_white"]
    roles: dict[str, str] = {name: role for name, role in zip(shuffled, roles_pool)}
    words: dict[str, str] = {
        name: (civilian_word if roles[name] == "civilian"
               else undercover_word if roles[name] == "undercover"
               else "")
        for name in all_players
    }

    suspicion_scores = {
        name: {other: 5 for other in all_players if other != name}
        for name in all_players
    }

    agent_colors = {a["name"]: a["color"] for a in AGENTS}
    agent_colors[HUMAN_PLAYER] = HUMAN_COLOR

    return GameState(
        game_id=str(uuid.uuid4()),
        round_number=1,
        surviving_agents=all_players.copy(),
        roles=roles,
        words=words,
        clues_history=[],
        clues_this_round=[],
        discussion_history=[],
        discuss_order=[],
        discuss_turn=0,
        suspicion_scores=suspicion_scores,
        votes_this_round={},
        votes_history=[],
        eliminated=[],
        game_over=False,
        winner=None,
        mr_white_guess=None,
        phase="speak",
        human_vote=None,
        agent_colors=agent_colors,
        civilian_word=civilian_word,
        undercover_word=undercover_word,
        pending_elimination=None,
    )


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _chat(model: str, system: str, user: str, stream: bool = False,
          temperature: float = 0.8) -> requests.Response:
    """Direct Ollama /api/chat call — mirrors voice_negotiation/core/llm.py style."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": stream,
        "options": {"temperature": temperature, "num_predict": 256},
    }
    return requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
        stream=stream,
    )


def _extract_tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


# ── Context builders ──────────────────────────────────────────────────────────

def _clue_context(state: GameState) -> str:
    if not state["clues_history"]:
        return "No clues have been given yet."
    return "\n".join(
        f"Round {e['round']} — {e['agent']}: \"{e['clue']}\""
        for e in state["clues_history"]
    )


def _discuss_context(state: GameState) -> str:
    if not state["discussion_history"]:
        return "No discussion yet."
    return "\n".join(
        f"[{e['agent']}]: {e['message']}"
        for e in state["discussion_history"]
    )


# ── Phase 1: Speaking ─────────────────────────────────────────────────────────

def generate_clue(state: GameState, agent_name: str) -> str:
    """Return a 1–2 word clue string for the agent."""
    role = state["roles"].get(agent_name, "civilian")
    word = state["words"].get(agent_name, "")
    personality = _AGENT_MAP[agent_name]["personality"]
    clue_ctx = _clue_context(state)

    if role == "mr_white":
        word_hint = (
            "You have NO secret word. Deduce the civilian word from clues you have heard "
            "and give a vague clue that could plausibly fit whatever the group knows."
        )
    elif role == "undercover":
        word_hint = (
            f"Your secret word is \"{word}\". Hint at YOUR word in a way that sounds "
            "plausible to civilians who have a different but related word."
        )
    else:
        word_hint = f"Your secret word is \"{word}\". Hint at it without being too obvious."

    system = f"""{personality}

You are playing Undercover — a social deduction game. {word_hint}

Clues given so far:
{clue_ctx}

OUTPUT RULES (strictly enforced):
- Output EXACTLY 1 or 2 words. No punctuation, no explanation.
- Do NOT say your secret word directly.
- Do NOT output anything other than the clue words."""

    try:
        resp = _chat(DISCUSSION_MODEL, system, "Give your clue now.", temperature=0.9)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "").strip()
        words = content.split()[:2]
        return " ".join(words) if words else "..."
    except Exception:
        return "..."


# ── Phase 2: Discussion (SSE streaming) ───────────────────────────────────────

def stream_discussion_turn(state: GameState, agent_name: str) -> Iterator[dict]:
    """
    Generator yielding token chunks then a final "done" chunk.
    Chunk shapes:
      {"token": str}
      {"done": True, "message": str, "suspicion": dict}
    """
    role = state["roles"].get(agent_name, "civilian")
    word = state["words"].get(agent_name, "")
    personality = _AGENT_MAP[agent_name]["personality"]
    survivors = ", ".join(state["surviving_agents"])
    eliminated_names = ", ".join(e["name"] for e in state["eliminated"]) or "none"
    clue_ctx = _clue_context(state)
    discuss_ctx = _discuss_context(state)

    if role == "mr_white":
        word_hint = (
            "You have NO secret word. Act as if you know the word. "
            "Steer suspicion toward civilians while blending in."
        )
    elif role == "undercover":
        word_hint = f"Your secret word is \"{word}\". Blend in with civilians; avoid detection."
    else:
        word_hint = f"Your secret word is \"{word}\". Expose inconsistencies to find the Undercover and Mr. White."

    system = f"""{personality}

You are playing Undercover. {word_hint}

Surviving players: {survivors}
Eliminated players: {eliminated_names}
Round: {state['round_number']}

Clues given:
{clue_ctx}

Discussion so far:
{discuss_ctx}

OUTPUT FORMAT (use this exact structure — no extra text before the tags):
<message>Your 1-3 sentence discussion contribution. You may address others as @Name.</message>
<suspicion>{{"AgentName": score_0_to_10, "AgentName2": score_0_to_10}}</suspicion>

Stay in character at all times. Keep the message to 1-3 sentences maximum."""

    full_text = ""
    try:
        resp = _chat(DISCUSSION_MODEL, system, "It's your turn to speak.", stream=True, temperature=0.85)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                full_text += token
                yield {"token": token}
                if chunk.get("done"):
                    break
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        full_text = "<message>I need to think about this more carefully.</message><suspicion>{}</suspicion>"
        yield {"token": "I need to think about this more carefully."}

    message = _extract_tag(full_text, "message")
    suspicion_raw = _extract_tag(full_text, "suspicion")

    if not message:
        # Fallback: strip tags and use raw text
        message = re.sub(r"<[^>]+>", "", full_text).strip()
        if not message:
            message = "I need to think about this more carefully."

    suspicion: dict = {}
    try:
        suspicion = json.loads(suspicion_raw) if suspicion_raw else {}
    except (json.JSONDecodeError, TypeError):
        pass

    yield {"done": True, "message": message, "suspicion": suspicion}


# ── Phase 3: Voting ───────────────────────────────────────────────────────────

def generate_vote(state: GameState, agent_name: str) -> dict:
    """Return {"vote": "AgentName", "reason": "one sentence"} for the agent."""
    personality = _AGENT_MAP[agent_name]["personality"]
    candidates = [s for s in state["surviving_agents"] if s != agent_name]
    suspicion = state["suspicion_scores"].get(agent_name, {})
    susp_text = ", ".join(f"{k}: {v}/10" for k, v in suspicion.items() if k in candidates)
    clue_ctx = _clue_context(state)
    discuss_ctx = _discuss_context(state)

    system = f"""{personality}

You are voting to eliminate a player from the Undercover game.
Vote for whoever you most suspect of being the Undercover agent or Mr. White.

Vote candidates: {", ".join(candidates)}
Your suspicion scores: {susp_text}

Clues:
{clue_ctx}

Discussion:
{discuss_ctx}

OUTPUT ONLY this JSON (no other text):
{{"vote": "ExactPlayerName", "reason": "One sentence reason."}}"""

    try:
        resp = _chat(VOTING_MODEL, system, "Cast your vote now.", temperature=0.3)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        data = _extract_json(content)
        vote = data.get("vote", "")
        reason = data.get("reason", "Seems suspicious based on their clue.")
        if vote in candidates:
            return {"vote": vote, "reason": reason}
    except Exception:
        pass

    # Fallback: vote for highest-suspicion candidate
    if candidates:
        target = max(candidates, key=lambda n: suspicion.get(n, 0))
        return {"vote": target, "reason": "Based on the pattern of clues, they stand out."}
    return {"vote": candidates[0] if candidates else agent_name,
            "reason": "Process of elimination."}


# ── Phase 4: Elimination ──────────────────────────────────────────────────────

def tally_votes(state: GameState) -> str:
    """Count votes_this_round and return the player to eliminate (random tie-break)."""
    tally: dict[str, int] = {}
    for target in state["votes_this_round"].values():
        tally[target] = tally.get(target, 0) + 1
    if not tally:
        return random.choice(state["surviving_agents"])
    max_votes = max(tally.values())
    top = [name for name, cnt in tally.items() if cnt == max_votes]
    return random.choice(top)


def generate_mr_white_guess(state: GameState) -> str:
    """Mr. White guesses the civilian word upon elimination."""
    clue_ctx = _clue_context(state)
    discuss_ctx = _discuss_context(state)

    system = """You are Mr. White, just eliminated from the Undercover game.
You must now guess what the civilian secret word was based on all clues and discussion.
Output ONLY a single word — your best guess. No punctuation, no explanation."""

    user = f"""Clues from the game:
{clue_ctx}

Discussion:
{discuss_ctx}

What is the civilian word?"""

    try:
        resp = _chat(DISCUSSION_MODEL, system, user, temperature=0.2)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "").strip()
        return content.split()[0] if content.split() else "unknown"
    except Exception:
        return "unknown"


def check_win(state: GameState) -> Optional[str]:
    """
    Return winner string or None.
    "civilians"  — both undercover and mr_white eliminated
    "undercover" — undercover survives to 2-player endgame
    Mr. White win is handled at elimination time (checked in routes.resolve_vote).
    """
    surviving_roles = {state["roles"][n] for n in state["surviving_agents"]}
    if "mr_white" not in surviving_roles and "undercover" not in surviving_roles:
        return "civilians"
    if "undercover" in surviving_roles and len(state["surviving_agents"]) <= 2:
        return "undercover"
    return None


def build_discuss_order(surviving_agents: list[str]) -> list[str]:
    """
    Return shuffled speaker order for discussion phase:
    (n_survivors × 2) turns via two shuffled passes.
    """
    first = surviving_agents.copy()
    random.shuffle(first)
    second = surviving_agents.copy()
    random.shuffle(second)
    return first + second


def apply_suspicion_updates(state: GameState, agent_name: str, updates: dict) -> None:
    """Merge suspicion score updates into state in-place."""
    bucket = state["suspicion_scores"].setdefault(agent_name, {})
    for target, raw_score in updates.items():
        if target in state["surviving_agents"] and target != agent_name:
            try:
                bucket[target] = max(0, min(10, int(raw_score)))
            except (ValueError, TypeError):
                pass
