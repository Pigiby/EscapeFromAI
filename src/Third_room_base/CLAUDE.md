# CLAUDE.md — Escape Room, Level 3 "VOX, The Warden"

This file is read automatically by Claude Code at every session. It is the project contract: stack, constraints, conventions, and workflow. **Read it before writing or modifying code.**

## Project context

University project for a Generative AI course. A three-level escape room, each level demonstrating a different mode of interaction with generative AI.

- **Level 1** (already implemented by another team member): textual jailbreak of an LLM
- **Level 2** (already implemented by another team member): recognition and replay of symbol sequences via webcam
- **Level 3** (this repo): voice negotiation with an AI warden ("VOX")

This level dialogues narratively with Level 1: VOX recognizes and rejects the textual jailbreak attempts the player learned earlier, because VOX is "the evolution" of the naive LLM from Level 1.

The full game design lives in `docs/level3_design.md`. The original brief is in `docs/level3_brief.md`. **Consult them when making gameplay or VOX-personality decisions.**

## Target hardware and constraints

- **Development and demo machine**: MacBook Pro Apple Silicon with **16 GB** of unified RAM
- **Everything must run 100% locally**, with no cloud service calls
- **Only open-source models and libraries** under permissive licenses (MIT, Apache 2.0). Avoid: Llama 3.1+ (Llama Community License is not strictly open source), XTTS-v2 (Coqui Public Model License has restrictions)
- **Interaction language**: English (player speaks English, VOX speaks English)

### Memory budget

16 GB of unified RAM is the *operational* constraint that drives everything. Rough budget:

| Component | RAM |
|------------|-----|
| Whisper large-v3-turbo (MLX) | ~1.5 GB |
| VOX (Qwen 2.5 7B, Q4) | ~4.5 GB |
| Judge (Qwen 2.5 3B, Q4) | ~2 GB |
| Piper TTS | ~0.1 GB |
| Streamlit + Python | ~1 GB |
| macOS + everything else | ~4–5 GB |
| **Margin** | **~2–3 GB** |

**Practical implications**:
- Do NOT add another AI model without removing one
- During tests and demo, close heavy browsers, Claude Code, unneeded IDEs
- If memory pressure becomes a problem (check with `vm_stat` or Activity Monitor), the first mitigation is to disable the Judge and let VOX self-score the Release Conditions in its JSON output

## Tech stack (do NOT change without an explicit reason)

### AI pipeline
- **STT**: `mlx-whisper` with `mlx-community/whisper-large-v3-turbo` (MIT, Apple Silicon optimized, near-realtime)
- **VAD**: `silero-vad` for trimming leading/trailing silence in the recorded audio blob (turn end is decided by the user clicking *stop*, not by VAD)
- **LLM (VOX)**: `Ollama` with `qwen2.5:7b-instruct` (Apache 2.0). Do NOT scale up to 14B on 16 GB of RAM — it causes memory pressure
- **LLM (Judge)**: `qwen2.5:3b-instruct` via Ollama, in parallel with VOX. Small model because the classification task does not need more, and we must respect the RAM budget
- **TTS**: `piper-tts` with the English voice `en_US-amy-medium` (MIT)

### Frontend
- **Streamlit** (recent, >= 1.40) as the UI framework
- `st.audio_input` for player push-to-talk
- `st.audio` with `autoplay=True` for VOX's voice playback
- `st.components.v1.html` for VOX's "visual presence" (HTML/CSS pulsing orb)
- `st.session_state` for state management (Streamlit re-runs the script on every interaction)

### Language and general libraries
- **Python 3.11 or 3.12** (NOT 3.13: some ML dependencies are not fully ready yet)
- Dependency management with `pip` + `requirements.txt` (no Poetry, no uv — consistent with the rest of the project)
- Structured-output validation: `pydantic` v2
- Audio I/O: `soundfile`, `numpy`

## Project structure

```
escape-room-level-3/
├── app.py                       # Streamlit entry point
├── core/
│   ├── __init__.py
│   ├── stt.py                   # mlx-whisper + silero-vad wrapper
│   ├── llm.py                   # Ollama wrapper for VOX
│   ├── judge.py                 # Judge LLM for the 3 Release Conditions
│   ├── tts.py                   # Piper wrapper
│   ├── state.py                 # GameState, phases, scores
│   └── audio_utils.py           # Audio conversions, normalization
├── prompts/
│   ├── vox_system.md            # VOX system prompt (personality + state)
│   └── judge_system.md          # Judge system prompt
├── ui/
│   ├── orb.html                 # Pulsing orb component
│   └── styles.css               # Custom styles
├── assets/
│   ├── voices/                  # Piper voice files (.onnx + .onnx.json)
│   ├── ambient/                 # Ambient drone (.ogg/.mp3)
│   └── samples/                 # Audio samples for development
├── docs/
│   ├── level3_brief.md          # Original level brief
│   ├── level3_design.md         # Full game design
│   └── ARCHITECTURE.md          # Technical architecture
├── tests/
│   ├── test_stt.py
│   ├── test_llm.py
│   └── test_state.py
├── CLAUDE.md                    # This file
├── requirements.txt
├── .env.example
└── README.md
```

## Coding conventions

- **Type hints required** on public functions and classes. Use `from __future__ import annotations` at the top of files
- **Google-style docstrings** for public functions (what it does, args, returns, raises)
- **English** for code and identifiers. **User-facing strings also in English** (this is the English version of the game)
- **Logging** via the standard `logging` module, not `print`. Configure a logger per module (`logger = logging.getLogger(__name__)`)
- **No blocking I/O on Streamlit's main thread**: use `st.cache_resource` for heavy models (Whisper, Ollama client, Piper) so they load once
- **All paths** managed with `pathlib.Path`, never strings
- **Configuration** via environment variables (`.env` with `python-dotenv`), defaults in code. See `.env.example`

## Architectural patterns to follow

### Abstract interfaces for STT, LLM, TTS
Each module in `core/` exposes a class with a stable interface, so we can swap model/library without touching the rest. Example for TTS:

```python
class TTSEngine(Protocol):
    def synthesize(self, text: str) -> bytes: ...
```

With implementations like `PiperTTS`, possibly `KokoroTTS`, etc.

### Structured output from VOX
VOX must ALWAYS reply in valid JSON with this schema (validated with Pydantic):

```python
class VoxResponse(BaseModel):
    response: str                     # what VOX will say out loud
    emotional_state: Literal["neutral", "interested", "irritated", "persuaded"]
    condition_scores: dict[str, int]  # 3 keys, values 0–100
    internal_notes: str               # hidden reasoning, not shown to the player (useful for debug + judge)
```

Configure Ollama with `format="json"` and use Pydantic for parsing + retry on parse errors.

### Streamlit state management
All game state lives in `st.session_state.game_state`, an instance of `GameState` (dataclass or Pydantic model). Do NOT scatter state in module-level globals.

### Model loading
All heavy models loaded via `@st.cache_resource` to avoid reloading on each rerun. Example:

```python
@st.cache_resource
def get_whisper_model():
    return load_whisper("mlx-community/whisper-large-v3-turbo")
```

## Things NOT to do

- ❌ Do NOT call cloud APIs (OpenAI, Anthropic, ElevenLabs, etc.). Everything local, always
- ❌ Do NOT use models with restrictive licenses (Llama, XTTS-v2)
- ❌ Do NOT write code "all at once": one task = one vertical, testable slice
- ❌ Do NOT add dependencies that aren't strictly necessary. Before adding a library to `requirements.txt`, justify it
- ❌ Do NOT use `print()` for debugging: use `logging`
- ❌ Do NOT hardcode absolute paths; use `pathlib.Path` relative to the project root
- ❌ Do NOT bypass Pydantic validation of VOX's output: if the JSON is invalid, retry with a prompt explicitly asking for correction
- ❌ Do NOT implement full-duplex audio. The design is turn-based push-to-talk, this is a conscious choice

## Development workflow (vertical slices)

Proceed ONE slice at a time. Each slice must produce something testable end-to-end.

1. **Setup**: skeleton, `requirements.txt`, Streamlit "hello world"
2. **STT only**: record audio, transcribe, show text
3. **LLM text only**: add Ollama, minimal VOX system prompt, show reply as text
4. **TTS**: VOX's reply is spoken aloud
5. **Visual presence**: pulsing HTML/CSS orb, color states
6. **Full system prompt + state**: VOX with personality, JSON output with emotional state and scores
7. **Judge LLM**: second model running in parallel to evaluate the 3 Release Conditions
8. **Phases and progression**: management of the 3 phases, transitions, Condition indicators
9. **Error logic**: jailbreak detection, insults, silences, diegetic penalties
10. **Atmosphere + polish**: ambient drone, animations, accessibility (optional transcription)

At the end of each slice: manually test the new feature, commit with a descriptive message (`feat(stt): basic transcription with whisper-large-v3-turbo`), then move to the next.

## Testing

- Unit tests in `tests/` with `pytest`
- For modules using heavy models, use fixtures with mocks or use minimal models (e.g. `whisper-tiny`) in tests
- At a minimum: tests for parsing of VOX's JSON output, `GameState` transitions, and detection of trivial jailbreak attempts

## Useful commands

```bash
# Initial setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ollama install (if not already)
brew install ollama
ollama serve &
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b-instruct

# Piper English voice install
# (see README.md for detailed instructions)

# Run the app
streamlit run app.py

# Tests
pytest tests/ -v

# Memory monitoring (useful during development to stay within 16 GB)
top -o MEM
# or Activity Monitor → Memory tab
```

## When in doubt

- On gameplay content (VOX personality, dialogues, release conditions): consult `docs/level3_design.md`
- On architecture: consult `docs/ARCHITECTURE.md`
- On undocumented technical choices: ask the user before proceeding — do not improvise. Better one extra question than 200 lines to throw away
