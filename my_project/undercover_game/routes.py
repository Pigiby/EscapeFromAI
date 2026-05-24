"""
Undercover AI — Level 4 Flask Blueprint.
All routes prefixed with /undercover.
Registered in server.py via app.register_blueprint(undercover_game_bp).
"""
from __future__ import annotations

import json
import os
import uuid

from flask import (
    Blueprint, Response, jsonify, redirect, request,
    send_from_directory, session, url_for,
)

from undercover_game.game import (
    AGENTS, HUMAN_PLAYER, HUMAN_COLOR, GameState,
    apply_suspicion_updates, build_discuss_order,
    check_win, generate_clue, generate_mr_white_guess, generate_vote,
    initialize_game, stream_discussion_turn, tally_votes,
)

undercover_game_bp = Blueprint(
    "undercover_game",
    __name__,
    url_prefix="/undercover",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Per-session game state registry. Lost on server restart — acceptable for demo.
GAME_STATE_REGISTRY: dict[str, GameState] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sid() -> str:
    if "room4_sid" not in session:
        session["room4_sid"] = str(uuid.uuid4())
    return session["room4_sid"]


def _get_state() -> GameState | None:
    return GAME_STATE_REGISTRY.get(_sid())


def _require_state() -> GameState:
    state = _get_state()
    if state is None:
        from flask import abort
        abort(400, "No active game — call POST /undercover/start first.")
    return state


def _public_state(state: GameState) -> dict:
    """State snapshot safe for the frontend."""
    n_survivors = len(state["surviving_agents"])
    return {
        "game_id": state["game_id"],
        "round_number": state["round_number"],
        "surviving_agents": state["surviving_agents"],
        "eliminated": state["eliminated"],
        "clues_history": state["clues_history"],
        "clues_this_round": state["clues_this_round"],
        "discussion_history": state["discussion_history"],
        "discuss_order": state["discuss_order"],
        "discuss_turn": state["discuss_turn"],
        "discuss_total": n_survivors * 2,
        "suspicion_scores": state["suspicion_scores"],
        "votes_this_round": state["votes_this_round"],
        "votes_history": state["votes_history"],
        "game_over": state["game_over"],
        "winner": state["winner"],
        "mr_white_guess": state["mr_white_guess"],
        "phase": state["phase"],
        "human_vote": state["human_vote"],
        "agent_colors": state["agent_colors"],
        "pending_elimination": state["pending_elimination"],
        # Always reveal the human player's own identity
        "player_role": state["roles"].get(HUMAN_PLAYER, "spectator"),
        "player_word": state["words"].get(HUMAN_PLAYER, ""),
        "human_alive": HUMAN_PLAYER in state["surviving_agents"],
        # Dev-mode fields (UI hides unless dev toggle is on)
        "_dev_roles": state["roles"],
        "_dev_words": state["words"],
        "_dev_civilian_word": state["civilian_word"],
        "_dev_undercover_word": state["undercover_word"],
    }


# ── Main page ─────────────────────────────────────────────────────────────────

@undercover_game_bp.route("/")
def undercover_index():
    if not session.get("level_3_complete"):
        return redirect(url_for("level_3"))
    return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")


# ── Game lifecycle ────────────────────────────────────────────────────────────

@undercover_game_bp.route("/start", methods=["POST"])
def start_game():
    state = initialize_game()
    GAME_STATE_REGISTRY[_sid()] = state
    return jsonify(_public_state(state))


@undercover_game_bp.route("/state", methods=["GET"])
def get_state():
    state = _require_state()
    return jsonify(_public_state(state))


# ── Phase 1: Speaking ─────────────────────────────────────────────────────────

@undercover_game_bp.route("/agent_clue", methods=["POST"])
def agent_clue():
    """Generate and record one agent's clue. Body: {"agent": "Name"}"""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent", "")
    if agent_name not in state["surviving_agents"]:
        return jsonify({"error": "Unknown or eliminated agent"}), 400

    clue = generate_clue(state, agent_name)
    entry = {"round": state["round_number"], "agent": agent_name, "clue": clue}
    state["clues_history"].append(entry)
    state["clues_this_round"].append({"agent": agent_name, "clue": clue})
    return jsonify({"agent": agent_name, "clue": clue, "color": state["agent_colors"].get(agent_name, "#fff")})


@undercover_game_bp.route("/clue_phase_done", methods=["POST"])
def clue_phase_done():
    """Finalize speaking phase, build discuss order, advance to discuss."""
    state = _require_state()
    order = build_discuss_order(state["surviving_agents"])
    state["discuss_order"] = order
    state["discuss_turn"] = 0
    state["phase"] = "discuss"
    return jsonify({"phase": "discuss", "discuss_order": order, "discuss_total": len(order)})


# ── Phase 2: Discussion (SSE) ─────────────────────────────────────────────────

@undercover_game_bp.route("/stream-turn")
def stream_turn():
    """
    SSE endpoint for one discussion turn.
    Query: ?agent=<name>
    Events:
      data: {"status":"token","token":"..."}
      data: {"status":"done","agent":"...","message":"...","suspicion":{...},"turn":N}
    """
    state = _require_state()
    agent_name = request.args.get("agent", "")
    if not agent_name or agent_name not in state["surviving_agents"]:
        def err():
            yield f'data: {json.dumps({"status":"error","msg":"invalid agent"})}\n\n'
        return Response(err(), mimetype="text/event-stream")

    turn_index = state["discuss_turn"]

    def generate():
        full_message = ""
        suspicion_updates: dict = {}

        for chunk in stream_discussion_turn(state, agent_name):
            if "token" in chunk:
                yield f'data: {json.dumps({"status":"token","token":chunk["token"]})}\n\n'
            elif chunk.get("done"):
                full_message = chunk.get("message", "")
                suspicion_updates = chunk.get("suspicion", {})

        # Commit to state
        entry = {
            "round": state["round_number"],
            "turn": turn_index,
            "agent": agent_name,
            "message": full_message,
        }
        state["discussion_history"].append(entry)
        apply_suspicion_updates(state, agent_name, suspicion_updates)
        state["discuss_turn"] = turn_index + 1

        payload = {
            "status": "done",
            "agent": agent_name,
            "color": state["agent_colors"].get(agent_name, "#fff"),
            "message": full_message,
            "suspicion": suspicion_updates,
            "turn": turn_index + 1,
        }
        yield f'data: {json.dumps(payload)}\n\n'

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@undercover_game_bp.route("/discuss_done", methods=["POST"])
def discuss_done():
    """Mark discussion complete, advance to vote phase."""
    state = _require_state()
    state["phase"] = "vote"
    state["votes_this_round"] = {}
    state["human_vote"] = None
    return jsonify({"phase": "vote"})


# ── Phase 3: Voting ───────────────────────────────────────────────────────────

@undercover_game_bp.route("/human-vote", methods=["POST"])
def human_vote():
    """Record the human player's vote. Body: {"vote": "AgentName"}"""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    target = data.get("vote", "")
    if target not in state["surviving_agents"]:
        return jsonify({"error": "Invalid vote target"}), 400
    state["human_vote"] = target
    state["votes_this_round"]["Human"] = target
    return jsonify({"ok": True, "voted_for": target})


@undercover_game_bp.route("/agent_vote", methods=["POST"])
def agent_vote():
    """Generate and record one agent's vote. Body: {"agent": "Name"}"""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    agent_name = data.get("agent", "")
    if agent_name not in state["surviving_agents"]:
        return jsonify({"error": "Unknown or eliminated agent"}), 400

    result = generate_vote(state, agent_name)
    state["votes_this_round"][agent_name] = result["vote"]
    state["votes_history"].append({
        "round": state["round_number"],
        "agent": agent_name,
        "vote": result["vote"],
        "reason": result["reason"],
    })
    return jsonify({
        "agent": agent_name,
        "vote": result["vote"],
        "reason": result["reason"],
        "color": state["agent_colors"].get(agent_name, "#fff"),
    })


@undercover_game_bp.route("/resolve", methods=["POST"])
def resolve_vote():
    """Tally votes, eliminate a player, check win conditions."""
    state = _require_state()

    eliminated_name = tally_votes(state)
    state["pending_elimination"] = eliminated_name
    role = state["roles"].get(eliminated_name, "unknown")
    mr_white_guess_word: str | None = None
    needs_human_mrwhite_guess = False

    if role == "mr_white":
        if eliminated_name == HUMAN_PLAYER:
            # Human Mr. White gets to guess via /human_mrwhite_guess — don't auto-generate
            needs_human_mrwhite_guess = True
            state["phase"] = "human_mr_white_guess"
        else:
            mr_white_guess_word = generate_mr_white_guess(state)
            state["mr_white_guess"] = mr_white_guess_word
            if mr_white_guess_word.lower() == state["civilian_word"].lower():
                state["game_over"] = True
                state["winner"] = "mr_white"

    # Remove from survivors and record elimination
    state["surviving_agents"] = [s for s in state["surviving_agents"] if s != eliminated_name]
    state["eliminated"].append({
        "name": eliminated_name,
        "role": role,
        "round": state["round_number"],
        "mr_white_guess": mr_white_guess_word,
    })

    # Win check only when we're not waiting on the human Mr. White guess
    if not needs_human_mrwhite_guess:
        if not state["game_over"]:
            winner = check_win(state)
            if winner:
                state["game_over"] = True
                state["winner"] = winner

        if not state["game_over"]:
            state["round_number"] += 1
            state["phase"] = "speak"
            state["clues_this_round"] = []
            state["votes_this_round"] = {}
            state["human_vote"] = None
            state["discuss_order"] = []
            state["discuss_turn"] = 0
        else:
            state["phase"] = "end"
            _on_game_end(state)

    return jsonify({
        "eliminated": eliminated_name,
        "role": role,
        "mr_white_guess": mr_white_guess_word,
        "needs_human_mrwhite_guess": needs_human_mrwhite_guess,
        "game_over": state["game_over"],
        "winner": state["winner"],
        "next_phase": state["phase"],
        "votes_tally": state["votes_this_round"],
        "civilian_word": state["civilian_word"] if state["game_over"] else None,
        "undercover_word": state["undercover_word"] if state["game_over"] else None,
    })


# ── Debug / shortcut routes ───────────────────────────────────────────────────

@undercover_game_bp.route("/human_clue", methods=["POST"])
def human_clue():
    """Record the human player's 1-2 word clue. Body: {"clue": "..."}"""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    raw = str(data.get("clue", "")).strip()
    clue = " ".join(raw.split()[:2]) if raw.split() else "..."
    entry = {"round": state["round_number"], "agent": HUMAN_PLAYER, "clue": clue}
    state["clues_history"].append(entry)
    state["clues_this_round"].append({"agent": HUMAN_PLAYER, "clue": clue})
    return jsonify({"agent": HUMAN_PLAYER, "clue": clue, "color": HUMAN_COLOR})


@undercover_game_bp.route("/human_mrwhite_guess", methods=["POST"])
def human_mrwhite_guess():
    """Human Mr. White submits their word guess after elimination."""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    raw = str(data.get("guess", "")).strip()
    guess = raw.split()[0].lower() if raw.split() else "unknown"
    state["mr_white_guess"] = guess

    correct = (guess == state["civilian_word"].lower())
    if correct:
        state["game_over"] = True
        state["winner"] = "mr_white"

    if not state["game_over"]:
        winner = check_win(state)
        if winner:
            state["game_over"] = True
            state["winner"] = winner

    if not state["game_over"]:
        state["round_number"] += 1
        state["phase"] = "speak"
        state["clues_this_round"] = []
        state["votes_this_round"] = {}
        state["human_vote"] = None
        state["discuss_order"] = []
        state["discuss_turn"] = 0
    else:
        state["phase"] = "end"
        _on_game_end(state)

    return jsonify({
        "guess": guess,
        "correct": correct,
        "game_over": state["game_over"],
        "winner": state["winner"],
        "next_phase": state["phase"],
        "civilian_word": state["civilian_word"] if state["game_over"] else None,
        "undercover_word": state["undercover_word"] if state["game_over"] else None,
    })


@undercover_game_bp.route("/human_message", methods=["POST"])
def human_message():
    """Record a human player's discussion message. Body: {"message": "..."}"""
    state = _require_state()
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[:500]
    if not message:
        return jsonify({"error": "Empty message"}), 400
    entry = {
        "round": state["round_number"],
        "turn": state.get("discuss_turn", 0),
        "agent": "Human",
        "message": message,
    }
    state["discussion_history"].append(entry)
    return jsonify({"ok": True, "agent": "Human", "message": message})


@undercover_game_bp.route("/force_vote", methods=["POST"])
def force_vote():
    """Skip directly to voting phase (dev / speed-run helper)."""
    state = _require_state()
    state["phase"] = "vote"
    state["votes_this_round"] = {}
    state["human_vote"] = None
    return jsonify({"phase": "vote"})


# ── Win/loss hooks ────────────────────────────────────────────────────────────

def _on_game_end(state: GameState) -> None:
    """
    Called when the game concludes.
    Marks level_4_complete in Flask session if civilians win.
    TODO: hook physical escape room hardware here.
    """
    if state["winner"] == "civilians":
        session["level_4_complete"] = True
        # on_game_success() — trigger external hardware/GPIO unlock here
    # else: on_game_failure() — trigger failure sequence here
