# Escape Room — Livello 3: "Il Custode"

Terzo livello di un'escape room basata su Generative AI. Il giocatore deve negoziare vocalmente con un'IA carceriera (VOX) per ottenere il codice di uscita.

**Stack**: Python 3.12 · Streamlit · MLX-Whisper · Ollama (Qwen 2.5) · Piper TTS

**Target**: macOS Apple Silicon, 16GB RAM (Mac Pro/Air M-series)

---

## Setup

### 1. Prerequisiti di sistema

```bash
# Homebrew (se non installato)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.12
brew install python@3.12

# Ollama (server LLM locale)
brew install ollama

# Piper TTS (binario)
brew install piper-tts
# In alternativa, scarica il binario da: https://github.com/rhasspy/piper/releases

# Dipendenze audio di sistema
brew install portaudio ffmpeg
```

### 2. Ambiente Python

```bash
cd escape-room-livello-3

# Crea virtualenv con Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Installa dipendenze
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Modelli Ollama (LLM)

```bash
# Avvia il server Ollama in background
ollama serve &

# Scarica i modelli (~4.5GB e ~2GB)
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b-instruct

# Verifica
ollama list
```

### 4. Voce italiana per Piper

```bash
mkdir -p assets/voices
cd assets/voices

# Voce 'Paola' (medium quality, ~63MB)
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json

cd ../..
```

### 5. Configurazione

```bash
cp .env.example .env
# Edita .env se vuoi cambiare i default
```

### 6. Verifica installazione

```bash
# Test rapido di ogni componente
python -c "import mlx_whisper; print('mlx-whisper OK')"
python -c "import ollama; print('ollama OK')"
python -c "import streamlit; print('streamlit OK')"

# Test Piper
echo "Ciao, sono il Custode." | piper \
  --model assets/voices/it_IT-paola-medium.onnx \
  --output_file /tmp/test_voice.wav
afplay /tmp/test_voice.wav
```

---

## Esecuzione

```bash
# Terminale 1: server Ollama
ollama serve

# Terminale 2: app Streamlit
source .venv/bin/activate
streamlit run app.py
```

L'app si apre su `http://localhost:8501`.

---

## Sviluppo

Vedi [`CLAUDE.md`](./CLAUDE.md) per il contratto del progetto, convenzioni di codice e workflow.

Vedi [`docs/level3_design.md`](./docs/level3_design.md) per il design completo del livello.

### Test

```bash
pytest tests/ -v
```

### Struttura

```
.
├── app.py                  # Entry point Streamlit
├── core/                   # Logica AI (STT, LLM, TTS, stato)
├── prompts/                # System prompt di VOX e Judge
├── ui/                     # Componenti HTML/CSS
├── assets/                 # Voci, audio ambient, sample
├── docs/                   # Brief, design, architettura
├── tests/                  # Test pytest
├── CLAUDE.md               # Contratto progetto (per Claude Code)
├── requirements.txt
└── README.md
```

---

## Troubleshooting

**Ollama: "connection refused"**
Assicurati che `ollama serve` sia in esecuzione in un altro terminale.

**`st.audio_input` non funziona**
Su Firefox c'è un bug noto con microfoni mono USB ([streamlit/issue #9799](https://github.com/streamlit/streamlit/issues/9799)). Usa Chrome o Safari.

**Latenza alta sul primo turno**
È normale: i modelli vengono caricati in memoria al primo uso. I turni successivi sono molto più rapidi grazie a `@st.cache_resource`.

**Piper non trova `espeak-ng`**
```bash
brew install espeak-ng
```

---

## Licenze

Tutti i componenti sono open source con licenze permissive:

- mlx-whisper: MIT
- Whisper (OpenAI): MIT
- Qwen 2.5: Apache 2.0
- Ollama: MIT
- Piper TTS: MIT
- Streamlit: Apache 2.0
- silero-vad: MIT

Codice di questo progetto: vedi [`LICENSE`](./LICENSE).
