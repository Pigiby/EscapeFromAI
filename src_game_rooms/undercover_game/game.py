"""
Undercover AI — Level 4 game logic.

Architecture:
- LangChain ChatOllama + ChatPromptTemplate + LCEL chains for all LLM calls.
- LangGraph StateGraph + MemorySaver for state persistence across Flask requests.
  State mutations happen via game_graph.update_state(); Flask routes drive the
  phase transitions rather than the graph itself, so per-agent animations and
  SSE streaming work without frontend changes.
"""
from __future__ import annotations

import json
import operator
import os
import random
import re
import uuid
from typing import Annotated, Iterator, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

# ── Word pairs (civilian_word, undercover_word) ───────────────────────────────

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

# ── Agent definitions ─────────────────────────────────────────────────────────

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
HUMAN_COLOR = "#c9a84c"

# ── LLM configuration ─────────────────────────────────────────────────────────

OLLAMA_HOST       = os.getenv("OLLAMA_HOST",       "http://localhost:11434").rstrip("/")
DISCUSSION_MODEL  = os.getenv("DISCUSSION_MODEL",  "llama3:8b")
VOTING_MODEL      = os.getenv("VOTING_MODEL",      "gemma3:1b")
OLLAMA_TIMEOUT    = int(os.getenv("OLLAMA_TIMEOUT", "120"))

# ── LangChain ChatOllama instances (one per temperature need) ─────────────────

_clue_llm = ChatOllama(
    base_url=OLLAMA_HOST, model=DISCUSSION_MODEL,
    temperature=0.9, num_predict=256,
)
_discuss_llm = ChatOllama(
    base_url=OLLAMA_HOST, model=DISCUSSION_MODEL,
    temperature=0.85, num_predict=256,
)
_vote_llm = ChatOllama(
    base_url=OLLAMA_HOST, model=VOTING_MODEL,
    temperature=0.3, num_predict=256,
)
_mrwhite_llm = ChatOllama(
    base_url=OLLAMA_HOST, model=DISCUSSION_MODEL,
    temperature=0.2, num_predict=256,
)

# ── LangChain Prompt Templates ────────────────────────────────────────────────

_clue_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "{personality}\n\n"
     "You are playing Undercover — a social deduction game. {word_hint}\n\n"
     "Clues given so far:\n{clue_ctx}\n\n"
     "OUTPUT RULES (strictly enforced):\n"
     "- Output EXACTLY 1 or 2 words. No punctuation, no explanation.\n"
     "- Do NOT say your secret word directly.\n"
     "- Do NOT output anything other than the clue words."),
    ("human", "Give your clue now."),
])

_discuss_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "{personality}\n\n"
     "You are playing Undercover. {word_hint}\n\n"
     "Surviving players: {survivors}\n"
     "Eliminated players: {eliminated_names}\n"
     "Round: {round_number}\n\n"
     "Clues given:\n{clue_ctx}\n\n"
     "Discussion so far:\n{discuss_ctx}\n\n"
     "OUTPUT FORMAT (use this exact structure — no extra text before the tags):\n"
     "<message>Your 1-3 sentence discussion. You may address others as @Name.</message>\n"
     "<suspicion>{{\"AgentName\": score_0_to_10, \"AgentName2\": score_0_to_10}}</suspicion>\n\n"
     "Stay in character at all times. Keep the message to 1-3 sentences maximum."),
    ("human", "It's your turn to speak."),
])

_vote_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "{personality}\n\n"
     "You are voting to eliminate a player from the Undercover game.\n"
     "Vote for whoever you most suspect of being the Undercover agent or Mr. White.\n\n"
     "Vote candidates: {candidates}\n"
     "Your suspicion scores: {susp_text}\n\n"
     "Clues:\n{clue_ctx}\n\n"
     "Discussion:\n{discuss_ctx}\n\n"
     "OUTPUT ONLY this JSON (no other text):\n"
     "{{\"vote\": \"ExactPlayerName\", \"reason\": \"One sentence reason.\"}}"),
    ("human", "Cast your vote now."),
])

_mrwhite_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are Mr. White, just eliminated from the Undercover game. "
     "You must now guess what the civilian secret word was based on all clues and discussion. "
     "Output ONLY a single word — your best guess. No punctuation, no explanation."),
    ("human",
     "Clues from the game:\n{clue_ctx}\n\n"
     "Discussion:\n{discuss_ctx}\n\n"
     "What is the civilian word?"),
])

# ── LCEL chains ───────────────────────────────────────────────────────────────

clue_chain    = _clue_prompt    | _clue_llm    | StrOutputParser()
vote_chain    = _vote_prompt    | _vote_llm    | StrOutputParser()
mrwhite_chain = _mrwhite_prompt | _mrwhite_llm | StrOutputParser()
# _discuss_llm is used directly with .stream() in stream_discussion_turn()

# ── LangGraph GameState (TypedDict with reducers) ─────────────────────────────

class GameState(TypedDict):
    game_id:             str
    round_number:        int
    surviving_agents:    list[str]
    roles:               dict[str, str]
    words:               dict[str, str]
    # Annotated lists use operator.add: update_state([entry]) appends
    clues_history:       Annotated[list[dict], operator.add]
    clues_this_round:    list[dict]        # replaced each round
    discussion_history:  Annotated[list[dict], operator.add]
    discuss_order:       list[str]
    discuss_turn:        int
    suspicion_scores:    dict              # full replacement on update
    votes_this_round:    dict[str, str]    # replaced each round
    votes_history:       Annotated[list[dict], operator.add]
    eliminated:          Annotated[list[dict], operator.add]
    game_over:           bool
    winner:              Optional[str]
    mr_white_guess:      Optional[str]
    phase:               str
    human_vote:          Optional[str]
    agent_colors:        dict[str, str]
    civilian_word:       str
    undercover_word:     str
    pending_elimination: Optional[str]


# ── LangGraph graph ───────────────────────────────────────────────────────────
# The graph has a single entry node. Phase transitions and per-agent actions
# are driven by Flask routes via game_graph.update_state(). The graph's
# MemorySaver checkpointer replaces the old in-memory GAME_STATE_REGISTRY.

def _entry_node(state: GameState) -> dict:
    """No-op entry node — state is managed externally via update_state()."""
    return {}


_builder = StateGraph(GameState)
_builder.add_node("game", _entry_node)
_builder.set_entry_point("game")
_builder.add_edge("game", END)

checkpointer = MemorySaver()
game_graph   = _builder.compile(checkpointer=checkpointer)

# ── Initial state factory ─────────────────────────────────────────────────────

def initialize_game() -> GameState:
    """Return a fresh GameState dict for a new 6-player game."""
    civilian_word, undercover_word = random.choice(WORD_PAIRS)
    all_players = [a["name"] for a in AGENTS] + [HUMAN_PLAYER]
    shuffled = all_players.copy()
    random.shuffle(shuffled)
    roles_pool = ["civilian", "civilian", "civilian", "civilian", "undercover", "mr_white"]
    roles: dict[str, str] = {name: role for name, role in zip(shuffled, roles_pool)}
    words: dict[str, str] = {
        name: (
            civilian_word   if roles[name] == "civilian"   else
            undercover_word if roles[name] == "undercover" else
            ""
        )
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

# ── Prompt context builders ───────────────────────────────────────────────────

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


def _word_hint(state: GameState, agent_name: str) -> str:
    role = state["roles"].get(agent_name, "civilian")
    word = state["words"].get(agent_name, "")
    if role == "mr_white":
        return (
            "You have NO secret word. Deduce the civilian word from clues you have heard "
            "and give a vague clue that could plausibly fit whatever the group knows."
        )
    if role == "undercover":
        return (
            f"Your secret word is \"{word}\". Hint at YOUR word in a way that sounds "
            "plausible to civilians who have a different but related word."
        )
    return f"Your secret word is \"{word}\". Hint at it without being too obvious."

# ── Output parsers ────────────────────────────────────────────────────────────

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

# ── Phase 1: Clue generation ──────────────────────────────────────────────────

def generate_clue(state: GameState, agent_name: str) -> str:
    """Invoke clue_chain (ChatPromptTemplate | ChatOllama | StrOutputParser)."""
    try:
        raw = clue_chain.invoke({
            "personality": _AGENT_MAP[agent_name]["personality"],
            "word_hint":   _word_hint(state, agent_name),
            "clue_ctx":    _clue_context(state),
        })
        words = raw.strip().split()[:2]
        return " ".join(words) if words else "..."
    except Exception:
        return "..."

# ── Phase 2: Discussion with SSE streaming ────────────────────────────────────

def stream_discussion_turn(state: GameState, agent_name: str) -> Iterator[dict]:
    """
    Generator that streams discussion tokens via _discuss_llm.stream().
    Yields:
      {"token": str}  — one per LLM token
      {"done": True, "message": str, "suspicion": dict}  — final chunk
    """
    messages = _discuss_prompt.format_messages(
        personality=      _AGENT_MAP[agent_name]["personality"],
        word_hint=        _word_hint(state, agent_name),
        survivors=        ", ".join(state["surviving_agents"]),
        eliminated_names= ", ".join(e["name"] for e in state["eliminated"]) or "none",
        round_number=     state["round_number"],
        clue_ctx=         _clue_context(state),
        discuss_ctx=      _discuss_context(state),
    )
    full_text = ""
    try:
        for chunk in _discuss_llm.stream(messages):
            token = chunk.content
            full_text += token
            yield {"token": token}
    except Exception:
        full_text = (
            "<message>I need to think about this more carefully.</message>"
            "<suspicion>{}</suspicion>"
        )
        yield {"token": "I need to think about this more carefully."}

    message = _extract_tag(full_text, "message")
    if not message:
        message = re.sub(r"<[^>]+>", "", full_text).strip() or "I need to think more carefully."

    suspicion: dict = {}
    try:
        raw_susp = _extract_tag(full_text, "suspicion")
        suspicion = json.loads(raw_susp) if raw_susp else {}
    except (json.JSONDecodeError, TypeError):
        pass

    yield {"done": True, "message": message, "suspicion": suspicion}

# ── Phase 3: Voting ───────────────────────────────────────────────────────────

def generate_vote(state: GameState, agent_name: str) -> dict:
    """Invoke vote_chain and return {"vote": str, "reason": str}."""
    candidates = [s for s in state["surviving_agents"] if s != agent_name]
    suspicion  = state["suspicion_scores"].get(agent_name, {})
    susp_text  = ", ".join(f"{k}: {v}/10" for k, v in suspicion.items() if k in candidates)
    try:
        raw = vote_chain.invoke({
            "personality": _AGENT_MAP[agent_name]["personality"],
            "candidates":  ", ".join(candidates),
            "susp_text":   susp_text,
            "clue_ctx":    _clue_context(state),
            "discuss_ctx": _discuss_context(state),
        })
        data   = _extract_json(raw)
        vote   = data.get("vote", "")
        reason = data.get("reason", "Seems suspicious based on their clue.")
        if vote in candidates:
            return {"vote": vote, "reason": reason}
    except Exception:
        pass

    if candidates:
        target = max(candidates, key=lambda n: suspicion.get(n, 0))
        return {"vote": target, "reason": "Based on the pattern of clues, they stand out."}
    return {
        "vote":   candidates[0] if candidates else agent_name,
        "reason": "Process of elimination.",
    }

# ── Phase 4: Elimination helpers ──────────────────────────────────────────────

def tally_votes(state: GameState) -> str:
    tally: dict[str, int] = {}
    for target in state["votes_this_round"].values():
        tally[target] = tally.get(target, 0) + 1
    if not tally:
        return random.choice(state["surviving_agents"])
    max_votes = max(tally.values())
    top = [name for name, cnt in tally.items() if cnt == max_votes]
    return random.choice(top)


def generate_mr_white_guess(state: GameState) -> str:
    """Invoke mrwhite_chain to guess the civilian word upon Mr. White's elimination."""
    try:
        raw = mrwhite_chain.invoke({
            "clue_ctx":    _clue_context(state),
            "discuss_ctx": _discuss_context(state),
        })
        return raw.strip().split()[0] if raw.strip().split() else "unknown"
    except Exception:
        return "unknown"


def check_win(state: GameState) -> Optional[str]:
    surviving_roles = {state["roles"][n] for n in state["surviving_agents"]}
    if "mr_white" not in surviving_roles and "undercover" not in surviving_roles:
        return "civilians"
    if len(state["surviving_agents"]) <= 2:
        if "undercover" in surviving_roles:
            return "undercover"
        if "mr_white" in surviving_roles:
            return "mr_white"
    return None


def build_discuss_order(surviving_agents: list[str]) -> list[str]:
    first  = surviving_agents.copy(); random.shuffle(first)
    second = surviving_agents.copy(); random.shuffle(second)
    return first + second


def apply_suspicion_updates(state: GameState, agent_name: str, updates: dict) -> dict:
    """Return a new suspicion_scores dict with updates merged in (non-mutating)."""
    scores = {k: dict(v) for k, v in state["suspicion_scores"].items()}
    bucket = scores.setdefault(agent_name, {})
    for target, raw_score in updates.items():
        if target in state["surviving_agents"] and target != agent_name:
            try:
                bucket[target] = max(0, min(10, int(raw_score)))
            except (ValueError, TypeError):
                pass
    return scores
