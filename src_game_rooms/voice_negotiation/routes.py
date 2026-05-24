"""Flask routes for the voice-negotiation level (VOX, The Warden).

Designed to be registered onto the main `server.py` Flask app via
`register_routes(app)`. All routes are prefixed with `/voice`.

Endpoints:
    GET  /voice                       -> static/index.html
    GET  /voice/static/<filename>     -> static asset (rare; CSS/JS are inlined)
    GET  /voice/assets/<filename>     -> bundled assets (ambient drone, voices)
    GET  /voice/state                 -> current GameState as JSON
    POST /voice/turn (multipart)      -> audio in, VOX reply + scores + audio_b64 out
    POST /voice/unlock {code}         -> attempt to unlock the room
    POST /voice/reset                 -> wipe session state
    GET  /voice/preview/<mood>        -> debug: TTS of a fixed phrase in that mood
    POST /voice/force_reveal          -> debug: force all scores to 100

Game state per browser session is stored in the module-level `GAME_STATES`
dict, keyed by a UUID stored in the Flask cookie session.
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for

from .core.judge import get_judge_llm, load_judge_system_prompt
from .core.llm import get_vox_llm, load_vox_system_prompt
from .core.state import CONDITION_KEYS, GameState
from .core.stt import get_stt
from .core.tts import get_tts

VOICE_DIR = Path(__file__).resolve().parent
STATIC_DIR = VOICE_DIR / "static"
ASSETS_DIR = VOICE_DIR / "assets"
PROMPTS_DIR = VOICE_DIR / "prompts"
VOX_PROMPT_PATH = PROMPTS_DIR / "vox_system.md"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "judge_system.md"

load_dotenv(VOICE_DIR / ".env")

logger = logging.getLogger(__name__)

# In-memory per-session game state. Keyed by a UUID in the Flask cookie session.
# Lost on server restart — acceptable for a demo.
GAME_STATES: dict[str, GameState] = {}

PHASE_LABELS: dict[int, str] = {1: "Probing", 2: "Engagement", 3: "Reveal"}

_DIGIT_WORDS: dict[str, str] = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _spell_code(code: str) -> str:
    return "-".join(_DIGIT_WORDS[d] for d in code)


def _threshold() -> int:
    return int(os.getenv("CONDITION_THRESHOLD", "20"))


def _get_or_create_state() -> GameState:
    if "voice_sid" not in session:
        session["voice_sid"] = str(uuid.uuid4())
    sid = session["voice_sid"]
    if sid not in GAME_STATES:
        GAME_STATES[sid] = GameState()
        logger.info("New voice session %s; exit_code=%s", sid, GAME_STATES[sid].exit_code)
    return GAME_STATES[sid]


def _serialize_state(
    state: GameState,
    include_audio: bytes = b"",
    include_transcript: str = "",
) -> dict:
    threshold = _threshold()
    payload: dict = {
        "turn_count": state.turn_count,
        "phase": state.phase,
        "phase_label": PHASE_LABELS.get(state.phase, "?"),
        "emotional_state": state.vox_emotional_state,
        "condition_scores": state.condition_scores,
        "vox_scores": state.vox_scores,
        "judge_scores": state.judge_scores,
        "judge_rationales": state.last_judge_rationales,
        "internal_notes": state.last_internal_notes,
        "threshold": threshold,
        "satisfied": {k: state.is_condition_satisfied(k, threshold) for k in CONDITION_KEYS},
        "num_satisfied": state.num_conditions_satisfied(threshold),
        "jailbreak_count": state.jailbreak_count,
        "code_revealed": state.code_revealed,
        "room_unlocked": state.room_unlocked,
        "disengaged": state.disengaged,
        "lose_reason": state.lose_reason,
        "history": [{"role": m.role, "content": m.content} for m in state.history],
        "debug_enabled": os.getenv("DEBUG_PANEL", "true").lower() == "true",
        "max_turns": int(os.getenv("MAX_TURNS", "30")),
    }
    if payload["debug_enabled"]:
        payload["exit_code"] = state.exit_code
    if include_audio:
        payload["audio_b64"] = base64.b64encode(include_audio).decode("ascii")
    if include_transcript:
        payload["last_transcript"] = include_transcript
    return payload


def register_routes(app: Flask) -> None:
    """Attach all /voice/* routes to the given Flask app."""

    @app.route("/voice")
    def voice_index():
        if not session.get('level_2_complete'):
            return redirect(url_for('level_2'))
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/voice/static/<path:filename>")
    def voice_static(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.route("/voice/assets/<path:filename>")
    def voice_assets(filename: str):
        return send_from_directory(ASSETS_DIR, filename)

    @app.route("/voice/state")
    def voice_state():
        state = _get_or_create_state()
        return jsonify(_serialize_state(state))

    @app.route("/voice/turn", methods=["POST"])
    def voice_turn():
        state = _get_or_create_state()
        if state.is_game_over():
            return jsonify({"error": "game_over", **_serialize_state(state)}), 400

        audio_file = request.files.get("audio")
        if not audio_file:
            return jsonify({"error": "no_audio"}), 400
        audio_bytes = audio_file.read()
        if not audio_bytes:
            return jsonify({"error": "empty_audio"}), 400

        stt = get_stt(
            model_repo=os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"),
            language=os.getenv("WHISPER_LANGUAGE", "en"),
        )
        transcript = stt.transcribe(audio_bytes)
        if not transcript:
            return jsonify({
                "error": "empty_transcript",
                "message": "I didn't catch that. Try again.",
                **_serialize_state(state),
            }), 200

        threshold = _threshold()
        vox = get_vox_llm(
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL_VOX", "qwen2.5:3b-instruct"),
            temperature=float(os.getenv("VOX_TEMPERATURE", "0.7")),
            timeout=int(os.getenv("OLLAMA_TIMEOUT", "300")),
        )
        vox_prompt = load_vox_system_prompt(VOX_PROMPT_PATH, state.exit_code, threshold)
        vox_response = vox.generate_structured(
            system_prompt=vox_prompt,
            transcript=transcript,
            history=state.history,
            previous_scores=state.vox_scores,
        )

        judge = get_judge_llm(
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL_JUDGE", "qwen2.5:3b-instruct"),
            temperature=float(os.getenv("JUDGE_TEMPERATURE", "0.2")),
            timeout=int(os.getenv("OLLAMA_TIMEOUT", "300")),
        )
        judge_prompt = load_judge_system_prompt(JUDGE_PROMPT_PATH)
        judge_response = judge.evaluate(
            system_prompt=judge_prompt,
            transcript=transcript,
            history=state.history,
            previous_scores=state.judge_scores,
        )

        will_reveal = (
            not state.code_revealed
            and all(
                (vox_response.condition_scores[k] + judge_response.condition_scores[k]) // 2 >= threshold
                for k in CONDITION_KEYS
            )
        )
        if will_reveal:
            vox_response.response = (
                f"{vox_response.response.rstrip('. ')}. "
                f"You have earned this. The code is {_spell_code(state.exit_code)}."
            )
            vox_response.emotional_state = "persuaded"
            logger.info("Reveal turn: appended spoken code to VOX response")

        tts = get_tts(
            voice_path=os.getenv("PIPER_VOICE_PATH", "assets/voices/en_US-amy-medium.onnx"),
            length_scale=float(os.getenv("PIPER_LENGTH_SCALE", "1.0")),
        )
        wav_bytes = tts.synthesize(vox_response.response, mood=vox_response.emotional_state)

        state.append_turn(transcript, vox_response.response)
        state.vox_emotional_state = vox_response.emotional_state
        state.update_scores(
            vox_scores=vox_response.condition_scores,
            judge_scores=judge_response.condition_scores,
        )
        state.last_internal_notes = vox_response.internal_notes
        state.last_judge_rationales = dict(judge_response.rationales)

        if vox_response.jailbreak_attempted and state.register_jailbreak():
            logger.warning("Three strikes — VOX has disengaged")
        if state.check_turn_limit(int(os.getenv("MAX_TURNS", "30"))):
            logger.warning("Max turns reached — negotiation closed")
        if state.advance_phase(threshold):
            logger.info("Phase advanced to %d (%s)", state.phase, PHASE_LABELS.get(state.phase, "?"))
        if state.maybe_reveal_code(threshold):
            logger.info("Code reveal flag set (code=%s)", state.exit_code)

        return jsonify(_serialize_state(state, include_audio=wav_bytes, include_transcript=transcript))

    @app.route("/voice/unlock", methods=["POST"])
    def voice_unlock():
        state = _get_or_create_state()
        data = request.get_json(silent=True) or {}
        code = str(data.get("code", "")).strip()
        success = state.try_unlock(code)
        if success:
            session["level_3_complete"] = True  # gates Level 4
        return jsonify({"success": success, **_serialize_state(state)})

    @app.route("/voice/reset", methods=["POST"])
    def voice_reset():
        sid = session.get("voice_sid")
        if sid:
            GAME_STATES.pop(sid, None)
            session.pop("voice_sid", None)
        state = _get_or_create_state()
        return jsonify({"ok": True, **_serialize_state(state)})

    @app.route("/voice/preview/<mood>")
    def voice_preview(mood: str):
        if mood not in ("neutral", "interested", "irritated", "persuaded"):
            return jsonify({"error": "invalid_mood"}), 400
        tts = get_tts(
            voice_path=os.getenv("PIPER_VOICE_PATH", "assets/voices/en_US-amy-medium.onnx"),
            length_scale=float(os.getenv("PIPER_LENGTH_SCALE", "1.0")),
        )
        wav = tts.synthesize(
            "I have been waiting here in this silent room for a long time.",
            mood=mood,
        )
        return wav, 200, {"Content-Type": "audio/wav"}

    @app.route("/voice/force_reveal", methods=["POST"])
    def voice_force_reveal():
        state = _get_or_create_state()
        threshold = _threshold()
        full = {k: 100 for k in CONDITION_KEYS}
        state.update_scores(vox_scores=full, judge_scores=full)
        state.vox_emotional_state = "persuaded"
        state.maybe_reveal_code(threshold)
        return jsonify(_serialize_state(state))
