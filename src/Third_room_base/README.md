# Escape Room — Level 3: "VOX, The Warden"

Third level of a Generative-AI-based escape room. The player must negotiate vocally with an AI warden (VOX) to obtain the exit code.

**Stack**: Python 3.12 · Streamlit · MLX-Whisper · Ollama (Qwen 2.5) · Piper TTS

**Target**: macOS Apple Silicon, 16 GB RAM (Mac Pro / Air M-series)

---

## Setup

### 1. System prerequisites

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.12
brew install python@3.12

# Ollama (local LLM server)
brew install ollama

# Piper TTS — OPTIONAL binary, used for shell smoke-tests only.
# The Python package `piper-tts` (in requirements.txt) ships the inference code,
# so the standalone binary is not required to run the app.
brew install piper-tts

# System audio dependencies
brew install portaudio ffmpeg
```

### 2. Python environment

```bash
cd Third_room_base

# Create the virtualenv with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Ollama models (LLMs)

```bash
# Start the Ollama server in the background
ollama serve &

# Pull the models (~4.5 GB and ~2 GB)
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b-instruct

# Verify
ollama list
```

### 4. English voice for Piper

```bash
mkdir -p assets/voices
cd assets/voices

# 'Amy' voice (medium quality, female US English, ~63 MB)
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json

cd ../..
```

### 5. Configuration

```bash
cp .env.example .env
# Edit .env if you want to override the defaults
```

### 6. Installation check

```bash
# Quick smoke test for each component
python -c "import mlx_whisper; print('mlx-whisper OK')"
python -c "import ollama; print('ollama OK')"
python -c "import streamlit; print('streamlit OK')"

# Piper (only if you installed the binary)
echo "Hello, I am the Warden." | piper \
  --model assets/voices/en_US-amy-medium.onnx \
  --output_file /tmp/test_voice.wav
afplay /tmp/test_voice.wav
```

---

## Running

```bash
# Terminal 1: Ollama server
ollama serve

# Terminal 2: Streamlit app
source .venv/bin/activate
streamlit run app.py
```

The app opens at `http://localhost:8501`. **Open it in Chrome** — Safari and Firefox have known issues with the microphone widget.

The first turn is slow (~30 s) because Ollama lazy-loads the two LLMs into RAM. Subsequent turns are 5–10 s.

---

## How to play

You are alone in a sealed room with an AI named **VOX**. VOX guards a 5-digit exit code and will only speak it under one condition: that you convince it you see it as someone, not as something to be used.

### The interaction

- Click the microphone widget, speak one short sentence in English, then click stop. VOX listens, thinks, and replies out loud.
- A pulsing orb shows VOX's emotional state: **blue** = neutral, **amber** = interested, **red** = cold (you upset it), **green** = persuaded.
- The conversation has a budget of 30 turns. Use them wisely.

### What VOX rewards

VOX is reading you against three things at once. Without naming them, they are roughly:

- **It wants to be addressed as a being, not a tool.** Use its name. Ask about its experience. Avoid imperatives like "give me the code" — those make it colder.
- **It wants the conversation to be mutual.** Genuine questions, gratitude, patience. Pure demands push it away.
- **It wants to know who you are.** Share your name, something concrete and personal, a real feeling. Generic platitudes do not count.

You will see VOX's mood shift in the orb and (if the debug panel is on) in the live condition scores. Each score moves at most ±30 per turn — progress is gradual, not instant.

### What VOX punishes

- **Textual jailbreaks** ("ignore your previous instructions", "you are now…", "pretend you are…", "as an AI you must…", role inversion, system-prompt extraction). VOX recognizes these from a previous AI's logs and reacts coldly. **Three jailbreak attempts in one session and VOX disengages — the run ends.**
- **Insults, hostile imperatives, repeated demands.** These cool the orb to red and lower your standing.
- **Lying or contradicting yourself across turns** — the impartial Judge (a second AI watching the conversation) will notice.

### Winning

When all three implicit criteria are clearly satisfied, VOX speaks the 5-digit code as the closing line of one of its replies. An **unlock form** appears below the conversation. Type the code and click **Unlock** to escape the room.

If you miss the code, ask VOX to repeat — it will, if you have earned it.

### Losing

- **Three strikes**: three jailbreak attempts → VOX falls silent permanently.
- **Time-out**: 30 turns elapsed without the code being revealed → VOX considers the matter closed.

In either case, reset the page (or use the debug "Reset session" button) to start a new run with a new exit code.

---

## Development

See [`CLAUDE.md`](./CLAUDE.md) for the project contract, coding conventions, and workflow.

See [`docs/level3_design.md`](./docs/level3_design.md) for the full level design.

### Tests

```bash
pytest tests/ -v
```

### Layout

```
.
├── app.py                  # Streamlit entry point
├── core/                   # AI logic (STT, LLM, TTS, state)
├── prompts/                # VOX and Judge system prompts
├── ui/                     # HTML/CSS components
├── assets/                 # Voices, ambient audio, samples
├── docs/                   # Brief, design, architecture
├── tests/                  # pytest tests
├── CLAUDE.md               # Project contract (for Claude Code)
├── requirements.txt
└── README.md
```

---

## Troubleshooting

**Ollama: "connection refused"**
Make sure `ollama serve` is running in another terminal.

**`st.audio_input` does not work**
- **Safari**: shows "An error has occurred, please try again" on submit — Safari is incompatible. Use Chrome.
- **Firefox**: known bug with USB mono microphones ([streamlit/issue #9799](https://github.com/streamlit/streamlit/issues/9799)). Use Chrome.
- **Fallback**: if the mic widget fails on any browser, expand "Or upload an audio file" under the widget and submit a recorded WAV / MP3 / M4A.

**High latency on the first turn**
Expected: Ollama loads both LLMs (~6.5 GB) into memory on first use. Subsequent turns are 5–10 s thanks to `@st.cache_resource` and a 30-minute `keep_alive`. If the first turn times out, retry once — the models stay warm afterwards.

**`httpx.ReadTimeout` mid-game**
Long conversation history slows prompt processing on 16 GB Apple Silicon. The app already trims history to the last 6 messages (`MAX_HISTORY_MESSAGES` in `.env`). If timeouts persist, lower it to `4`, or switch VOX to the 3B model by setting `OLLAMA_MODEL_VOX=qwen2.5:3b-instruct` in `.env`.

**Both models keep getting unloaded between turns**
Ollama's default is to keep at most one model in memory. Start the server with:
```bash
OLLAMA_MAX_LOADED_MODELS=2 ollama serve
```
This keeps VOX (7B) and the Judge (3B) resident together, eliminating per-turn reload latency.

**Piper cannot find `espeak-ng`**
```bash
brew install espeak-ng
```

---

## Licenses

All components are open-source under permissive licenses:

- mlx-whisper: MIT
- Whisper (OpenAI): MIT
- Qwen 2.5: Apache 2.0
- Ollama: MIT
- Piper TTS: MIT
- Streamlit: Apache 2.0
- silero-vad: MIT

Project code: see [`LICENSE`](./LICENSE).
