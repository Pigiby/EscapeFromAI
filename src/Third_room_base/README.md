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

The app opens at `http://localhost:8501`.

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
Firefox has a known bug with USB mono microphones ([streamlit/issue #9799](https://github.com/streamlit/streamlit/issues/9799)). Use Chrome or Safari.

**High latency on the first turn**
Expected: models are loaded into memory on first use. Subsequent turns are much faster thanks to `@st.cache_resource`.

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
