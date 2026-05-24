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

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
```

#### Download the required models

The game uses **FLUX.1 Canny Dev**. You need four model files placed in specific folders inside `ComfyUI/`.

Install the Hugging Face CLI if you don't have it, then log in (required for the gated FLUX model):

```bash
pip install huggingface_hub
huggingface-cli login
```

Then download each file:

```bash
# 1. Diffusion model → ComfyUI/models/unet/
huggingface-cli download black-forest-labs/FLUX.1-Canny-dev \
  flux1-canny-dev.safetensors \
  --local-dir ComfyUI/models/unet

# 2. VAE → ComfyUI/models/vae/
huggingface-cli download black-forest-labs/FLUX.1-dev \
  ae.safetensors \
  --local-dir ComfyUI/models/vae

# 3. CLIP text encoders → ComfyUI/models/clip/
huggingface-cli download comfyanonymous/flux_text_encoders \
  clip_l.safetensors t5xxl_fp16.safetensors \
  --local-dir ComfyUI/models/clip
```

> `flux1-canny-dev.safetensors` is ~23 GB. `t5xxl_fp16.safetensors` is ~10 GB. Total: ~35 GB.  
> The FLUX model is gated — accept the license at [huggingface.co/black-forest-labs/FLUX.1-Canny-dev](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev) before downloading.

Start ComfyUI on port 8000 (keep this terminal open):

```bash
python3 main.py --port 8000
```

---

### 3. Install Python dependencies

```bash
cd src_game_rooms
pip install -r requirements.txt
```

> Requires Python ≥ 3.11. Level 3 uses `mlx-whisper` which requires Apple Silicon — on other platforms replace it with `openai-whisper` in `requirements.txt`.

---

### 4. Launch the game

```bash
cd src_game_rooms
python3 server.py
```

Open **http://localhost:8080** in your browser.
