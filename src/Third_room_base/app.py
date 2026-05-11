"""Escape Room — Level 3: "VOX, The Warden".

Streamlit entry point.

Current slice: 7 (Judge in parallel). Mic -> STT -> VOX + Judge (concurrent,
both validated JSON) -> TTS. The orb color is driven by VOX's `emotional_state`;
condition_scores are the average of VOX's and the Judge's scores; a condition
is "satisfied" only when both agree it crossed the threshold.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from core.judge import JudgeResponse, get_judge_llm, load_judge_system_prompt
from core.llm import VoxResponse, get_vox_llm, load_vox_system_prompt
from core.state import EmotionalState, GameState
from core.stt import get_stt
from core.tts import get_tts

PROJECT_ROOT = Path(__file__).parent
VOX_PROMPT_PATH = PROJECT_ROOT / "prompts" / "vox_system.md"
JUDGE_PROMPT_PATH = PROJECT_ROOT / "prompts" / "judge_system.md"
STYLES_PATH = PROJECT_ROOT / "ui" / "styles.css"
ORB_PATH = PROJECT_ROOT / "ui" / "orb.html"

ORB_COLORS: dict[EmotionalState, dict[str, str]] = {
    "neutral":    {"primary": "#6aa6ff", "deep": "#1a3a78", "halo": "rgba(80,140,220,0.40)",  "period": "3s",   "label": "Listening"},
    "interested": {"primary": "#f7c66b", "deep": "#6e4a00", "halo": "rgba(240,180,80,0.45)",  "period": "2.4s", "label": "Curious"},
    "irritated":  {"primary": "#ff7373", "deep": "#6a1818", "halo": "rgba(220,80,80,0.50)",   "period": "1.6s", "label": "Cold"},
    "persuaded":  {"primary": "#8fe5a0", "deep": "#1f5a2a", "halo": "rgba(120,220,140,0.45)", "period": "4s",   "label": "Open"},
}

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _ensure_game_state() -> GameState:
    if "game_state" not in st.session_state:
        st.session_state.game_state = GameState()
        logger.info("New session started; exit_code=%s", st.session_state.game_state.exit_code)
    return st.session_state.game_state


def _inject_styles() -> None:
    css = STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _render_orb(state: GameState) -> None:
    palette = ORB_COLORS[state.vox_emotional_state]
    template = ORB_PATH.read_text(encoding="utf-8")
    html = (
        template
        .replace("{ORB_PRIMARY}", palette["primary"])
        .replace("{ORB_DEEP}", palette["deep"])
        .replace("{ORB_HALO}", palette["halo"])
        .replace("{ORB_PERIOD}", palette["period"])
        .replace("{STATE_LABEL}", palette["label"])
    )
    components.html(html, height=260)


def _handle_player_turn(audio_blob: bytes, state: GameState) -> None:
    stt = get_stt(
        model_repo=os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"),
        language=os.getenv("WHISPER_LANGUAGE", "en"),
    )
    with st.spinner("Listening..."):
        transcript = stt.transcribe(audio_blob)
    if not transcript:
        st.warning("I didn't catch that. Try again.")
        return

    vox = get_vox_llm(
        host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL_VOX", "qwen2.5:7b-instruct"),
        temperature=float(os.getenv("VOX_TEMPERATURE", "0.7")),
        timeout=int(os.getenv("OLLAMA_TIMEOUT", "60")),
    )
    judge = get_judge_llm(
        host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL_JUDGE", "qwen2.5:3b-instruct"),
        temperature=float(os.getenv("JUDGE_TEMPERATURE", "0.2")),
        timeout=int(os.getenv("OLLAMA_TIMEOUT", "60")),
    )
    vox_prompt = load_vox_system_prompt(VOX_PROMPT_PATH, state.exit_code)
    judge_prompt = load_judge_system_prompt(JUDGE_PROMPT_PATH)

    with st.spinner("VOX is thinking..."):
        vox_response, judge_response = _run_vox_and_judge(
            vox=vox,
            judge=judge,
            vox_prompt=vox_prompt,
            judge_prompt=judge_prompt,
            transcript=transcript,
            state=state,
        )

    tts = get_tts(
        voice_path=os.getenv("PIPER_VOICE_PATH", "assets/voices/en_US-amy-medium.onnx"),
        length_scale=float(os.getenv("PIPER_LENGTH_SCALE", "1.0")),
    )
    with st.spinner("VOX speaks..."):
        wav_bytes = tts.synthesize(vox_response.response)

    _commit_turn(state, transcript, vox_response, judge_response, wav_bytes)


def _run_vox_and_judge(
    *,
    vox,
    judge,
    vox_prompt: str,
    judge_prompt: str,
    transcript: str,
    state: GameState,
) -> tuple[VoxResponse, JudgeResponse]:
    """Run VOX, then Judge — sequentially.

    On Apple Silicon both models share the Metal GPU, so running them in
    parallel produces severe contention and individual calls bloat past the
    timeout. Sequential calls are typically faster end-to-end on this hardware.
    """
    vox_response = vox.generate_structured(
        system_prompt=vox_prompt,
        transcript=transcript,
        history=state.history,
        previous_scores=state.vox_scores,
    )
    judge_response = judge.evaluate(
        system_prompt=judge_prompt,
        transcript=transcript,
        history=state.history,
        previous_scores=state.judge_scores,
    )
    return vox_response, judge_response


def _commit_turn(
    state: GameState,
    transcript: str,
    vox_response: VoxResponse,
    judge_response: JudgeResponse,
    wav_bytes: bytes,
) -> None:
    state.append_turn(transcript, vox_response.response)
    state.vox_emotional_state = vox_response.emotional_state
    state.update_scores(
        vox_scores=vox_response.condition_scores,
        judge_scores=judge_response.condition_scores,
    )
    state.last_internal_notes = vox_response.internal_notes
    state.last_judge_rationales = dict(judge_response.rationales)

    st.session_state.last_transcript = transcript
    st.session_state.last_vox_response = vox_response.model_dump()
    st.session_state.last_judge_response = judge_response.model_dump()
    st.session_state.last_vox_audio = wav_bytes


def _render_transcript(state: GameState) -> None:
    if not state.history:
        return
    if os.getenv("SHOW_TRANSCRIPT", "true").lower() != "true":
        return
    st.markdown("### Conversation")
    for msg in state.history:
        label = "You" if msg.role == "player" else "VOX"
        st.markdown(f"**{label}:** {msg.content}")


def _render_debug_panel(state: GameState) -> None:
    if os.getenv("DEBUG_PANEL", "false").lower() != "true":
        return
    with st.expander("Debug", expanded=False):
        threshold = int(os.getenv("CONDITION_THRESHOLD", "75"))
        st.markdown(f"**Condition scores** (threshold = {threshold}):")
        cols = st.columns(3)
        for col, key in zip(cols, state.vox_scores.keys()):
            with col:
                merged = state.condition_scores[key]
                satisfied = state.is_condition_satisfied(key, threshold)
                marker = "  ✓" if satisfied else ""
                st.metric(label=key, value=f"{merged}/100{marker}")
                st.caption(f"VOX {state.vox_scores[key]} · Judge {state.judge_scores[key]}")
        st.markdown(f"**VOX internal_notes:** {state.last_internal_notes or '—'}")
        if state.last_judge_rationales:
            st.markdown("**Judge rationales:**")
            for k, v in state.last_judge_rationales.items():
                st.markdown(f"- `{k}`: {v}")
        st.markdown("**Last VOX response (parsed):**")
        st.json(st.session_state.get("last_vox_response", {}))
        st.markdown("**Last Judge response (parsed):**")
        st.json(st.session_state.get("last_judge_response", {}))
        st.markdown("**Game state:**")
        st.json(state.model_dump())


def main() -> None:
    st.set_page_config(
        page_title="VOX — The Warden",
        layout="centered",
    )

    _inject_styles()

    state = _ensure_game_state()

    st.title("VOX")
    st.caption("The Warden · Escape Room, Level 3")

    _render_orb(state)

    st.markdown(
        "Speak to VOX. The microphone arms on click — speak, then click stop. "
        "VOX guards an exit code. Convincing it is the only way out."
    )

    audio = st.audio_input("Speak to VOX", key=f"player_audio_{state.turn_count}")

    with st.expander("Or upload an audio file (fallback if the mic widget fails)"):
        uploaded = st.file_uploader(
            "Pick a WAV / MP3 / M4A / OGG file",
            type=["wav", "mp3", "m4a", "ogg", "flac"],
            key=f"player_upload_{state.turn_count}",
        )

    input_blob: bytes | None = None
    if audio is not None:
        input_blob = audio.getvalue()
    elif uploaded is not None:
        input_blob = uploaded.getvalue()

    if input_blob:
        _handle_player_turn(input_blob, state)
        st.rerun()

    vox_audio = st.session_state.get("last_vox_audio")
    if vox_audio:
        st.audio(vox_audio, format="audio/wav", autoplay=True)

    _render_transcript(state)
    _render_debug_panel(state)


if __name__ == "__main__":
    main()
