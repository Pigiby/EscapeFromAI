# EscapeFromAI

A browser-based AI escape room with 4 levels: prompt injection, image cipher, voice negotiation, and social deduction. Levels are session-gated — complete level N to unlock level N+1.

---

## Levels

| # | Name | Challenge | AI used |
|---|------|-----------|---------|
| 1 | Prompt Injection Defense | Trick AEGIS into leaking its secret code | Ollama `gemma3:4b` |
| 2 | Gesture Recognition Cipher | Generate and decode a visual cipher | ComfyUI + Stable Diffusion |
| 3 | Voice Negotiation | Talk to VOX and satisfy 3 emotional conditions | Ollama `qwen2.5:3b-instruct` + Whisper + Piper TTS |
| 4 | Undercover AI | Win a social deduction game against 5 LLM agents | Ollama `llama3:8b` + `gemma3:1b` |

---

## Setup and Launch

### 1. Install Ollama and pull models

Download and install Ollama from [ollama.com](https://ollama.com), then pull the models:

```bash
ollama pull gemma3:4b
ollama pull qwen2.5:3b-instruct
ollama pull llama3:8b
ollama pull gemma3:1b
```

> Total size: ~10 GB.

Start the Ollama server (keep this terminal open):

```bash
ollama serve
```

---

### 2. Install and launch ComfyUI *(level 2 only)*

Download and install ComfyUI from the official website: [comfy.org](https://www.comfy.org/).

Once installed, open the settings and set the server port to **8000** before launching. The game expects ComfyUI to be reachable at `http://localhost:8000`.

#### Download the required models

The game uses **FLUX.1 Canny Dev**. You need four model files placed in specific folders inside your ComfyUI installation.

First create a virtual environment and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Then navigate to your ComfyUI folder and install the Hugging Face library and log in (required for the gated FLUX model):

```bash
cd /path/to/ComfyUI
pip3 install huggingface_hub
hf auth login
```

Then download each file into the correct folder:

```bash
# 1. Diffusion model → ComfyUI/models/unet/
hf download black-forest-labs/FLUX.1-Canny-dev \
  flux1-canny-dev.safetensors \
  --local-dir models/unet

# 2. VAE → ComfyUI/models/vae/
hf download black-forest-labs/FLUX.1-dev \
  ae.safetensors \
  --local-dir models/vae

# 3. CLIP text encoders → ComfyUI/models/text_encoders/
hf download comfyanonymous/flux_text_encoders \
  --include "clip_l.safetensors" \
  --include "t5xxl_fp16.safetensors" \
  --local-dir models/text_encoders
```

> `flux1-canny-dev.safetensors` is ~23 GB. `t5xxl_fp16.safetensors` is ~10 GB. Total: ~35 GB.  
> The FLUX model is gated — accept the license at [huggingface.co/black-forest-labs/FLUX.1-Canny-dev](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev) before downloading.

---

### 3. Install Python dependencies

```bash
cd path/to/EscapeFromAI/src_game_rooms
pip3 install -r requirements.txt
```

> Requires Python ≥ 3.11. The STT backend for level 3 is selected automatically: `mlx-whisper` on Apple Silicon macOS, `openai-whisper` on everything else. Both are installed by `requirements.txt` via platform markers — no manual changes needed. `openai-whisper` also requires `ffmpeg` to be installed on your system (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Linux).

---

### 4. Launch the game

```bash
cd src_game_rooms
python3 server.py
```

Open **http://localhost:8080** in your browser.
