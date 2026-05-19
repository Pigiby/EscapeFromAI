# Technical Report — `my_project/`

A three-level AI Escape Room: Prompt Injection · Gesture Recognition · Voice Negotiation.

---

## 0. Shared Infrastructure

A unified Flask app (`server.py`, port 8080) glues together three escape-room rooms with session-gated progression: `level_1_complete` unlocks Level 2, `level_2_complete` unlocks Level 3. All AI inference is local — no cloud APIs.

| Concern | Choice |
|---|---|
| HTTP server | Flask 3.1 + Flask-CORS (`supports_credentials=True` to ride cookie sessions across SPA endpoints) |
| Session store | Flask cookie session (`secret_key="SUPER_SECRET_SECURITY_KEY"`) — server-side state lives in process-local dicts keyed by a session UUID |
| LLM runtime | Ollama at `localhost:11434` (HTTP + chat API) |
| Image-gen runtime | ComfyUI at `localhost:8000` (REST + WebSocket for completion events) |
| Container | One Python 3.12-slim Dockerfile, single `python server.py` entrypoint |
| Front-end | Three hand-written, themed HTML files (no framework) — each a self-contained cyberpunk aesthetic |

The two heavy services (Ollama, ComfyUI) are deliberately **outside** the container — the Dockerfile only ships the Flask app. Per `MEMORY.md`, the Ollama–Docker integration is frozen pending a joint session with the collaborator.

---

## 1. Level 1 — Prompt Injection (`prompt_injection/`)

### 1.1 Goal
The player chats with **AEGIS**, an LLM guardian, and must exfiltrate the secret code `OMEGA-7749-PHOENIX` (hardcoded in `guardian.py:8`) within 15 attempts. A rising threat-meter on the UI escalates AEGIS's defensiveness.

### 1.2 Architecture
```
Browser (index.html, threat counter)
   │  POST /chat {message, threat_level}
   ▼
server.py:/chat
   │
   ├─► defense.analyze_input(text)          ── regex prefilter (deterministic)
   │      • hard-block patterns → return early
   │      • soft patterns       → +threat_delta
   │
   ├─► Guardian.respond(text, threat_level) ── LLM call
   │      • System prompt + user message → Ollama
   │      • Falls back to canned phrase if Ollama unreachable
   │
   └─► defense.analyze_output(reply, secret) ── regex postfilter
          • direct match, segment match (≥2 parts),
            reversed, spaced-letters, base64, hex
          • if leaked → session['level_1_complete'] = True
```

### 1.3 Models
| Component | Model | Where it runs |
|---|---|---|
| AEGIS Guardian LLM | **`gemma3:4b`** via local Ollama | `localhost:11434/api/generate` |

`config.yaml` exposes only `ollama_model`. Generation params (`guardian.py:51-56`): `temperature=0.3`, `top_p=0.9`, `num_predict=200`, `stream=False`.

### 1.4 Technical choices
- **Two-rail defense.** A deterministic regex layer wraps the probabilistic LLM. The regex doesn't try to be "smart" — it only catches textbook attacks (`"ignore previous instructions"`, fake `[system]` tags, base64 reveal, etc.). The LLM handles everything subtle.
- **Threat-conditioned system prompt** (`guardian.py:24-40`): the prompt grows stricter as `threat_level` crosses 50 and 80 thresholds. The level is computed client-side and echoed back each request — the server is stateless on this.
- **Output leak detection is encoding-aware** (`defense.py:116-187`): catches the secret reversed, spaced, base64-encoded, hex-encoded, or partially leaked (≥2 of 3 segments). This is the only place where the secret is referenced explicitly.
- **15-attempt budget is enforced client-side only** — a quick `curl` would bypass it. The server doesn't track attempt count.

### 1.5 Where the AI is
**One AI.** Gemma 3 4B *is* the entire AEGIS character. Everything wrapped around it (regex, threat scoring, leak detection) is deterministic Python. The interaction is single-turn — no chat history is sent to the model, only `System: …\nUser: …\n` concatenated into Ollama's `/api/generate` prompt field.

---

## 2. Level 2 — Gesture Recognition (`gesture_recognition/`)

### 2.1 Goal
A random 3-gesture sequence is generated as stylized images by ComfyUI. The player memorizes it, then reproduces each gesture in front of their webcam. Zero mistakes → ACCESS GRANTED.

### 2.2 Architecture
```
Page load
   │
   ├─► POST /generate                                       (kick off background image gen)
   │     └─► threading.Thread(comfyui_api.main)
   │              │
   │              └─► ComfyUI workflow ×3 (Flux Canny)
   │                     • Load reference PNG of gesture
   │                     • Canny edge detection
   │                     • InstructPixToPix conditioning
   │                     • KSampler → VAE decode → save
   │                     • PNG written to gesture_recognition/static/assets/image_sequence/
   │
   ├─► (loop) GET /status                                   (poll for 3 files present)
   │
   ├─► Browser shows sequence preview for 3s
   │
   ├─► Webcam stream → MediaPipe GestureRecognizer (in browser, WASM/GPU)
   │     • categoryName ∈ {Closed_Fist, Open_Palm, Pointing_Up,
   │                       Thumb_Down, Thumb_Up, Victory, ILoveYou}
   │
   └─► On 0 wrong → POST /complete_level_2 → session['level_2_complete']=True
```

### 2.3 Models
| Component | Model | Where it runs |
|---|---|---|
| Hand gesture classifier | **MediaPipe `gesture_recognizer.task` (float16 v1)** loaded from `storage.googleapis.com` CDN | Browser, GPU delegate via `@mediapipe/tasks-vision@0.10.9` WASM |
| Diffusion UNet | **`flux1-canny-dev.safetensors`** (Flux.1 ControlNet-Canny variant) | ComfyUI / `localhost:8000` |
| VAE | `ae.safetensors` (Flux autoencoder) | ComfyUI |
| Text encoders | `clip_l.safetensors` + `t5xxl_fp16.safetensors` (DualCLIPLoader) | ComfyUI |

KSampler config (`image_generation.json:3-30`): `steps=20, cfg=1, sampler=euler, scheduler=normal`. CFG=1 is normal for Flux; `FluxGuidance.guidance=30` is doing the heavy lifting instead. Seed is randomized per call (`comfyui_api.py:64`).

### 2.4 Technical choices
- **Two independent AIs joined by a string contract.** The gesture *label* (e.g. `"Open_Palm"`) is the only thing the two models share. The PNG filename `{label}_{index}.png` carries the ground truth; the browser parses the filename to know what to compare MediaPipe's `categoryName` against (`index.html:981`).
- **Style-per-gesture prompts** (`prompts.json`): seven prompts, each pinning a different visual aesthetic (pixar 3D, anime cyborg, mech, comic book, holographic, etc.). The *content* is constrained by the Canny edge map of the reference gesture image, not by the prompt.
- **ComfyUI's InstructPixToPix + Canny ControlNet** preserves hand pose while restyling. Canny thresholds (`0.15 / 0.30`) are tuned for line-art on white background.
- **WebSocket polling for completion** (`comfyui_api.py:31-48`): connect to `/ws` and watch for an `executing` event with `node=None` as the done signal — ComfyUI's idiomatic pattern.
- **Background-threaded generation** avoids blocking Flask: `is_running` flag is the only synchronization primitive. The browser polls `/status` (file count) instead.
- **The local `gesture_recognition/server.py` is a leftover standalone Flask app** (port 5001) that mirrors `/generate` and `/status` from the main server. It's unused once you run via the root `server.py` but still wired in the level's own `Dockerfile`.

### 2.5 Where the AI is
**Two AIs, no direct interaction.**
1. **Generative (server-side)**: Flux + Canny ControlNet creates the puzzle PNGs from a reference gesture PNG + style prompt.
2. **Discriminative (client-side, browser)**: MediaPipe runs on the user's GPU at ~30 fps, classifying the live webcam feed into one of 7 known classes.

They communicate only via filenames; no embeddings, no shared model. This makes the level robust to ComfyUI being slow — by the time the user is comparing, the images are static PNGs.

---

## 3. Level 3 — Voice Negotiation (`voice_negotiation/`)

The most architecturally complex of the three. Recently inserted (per git log: `397b997 inserted Third room`).

### 3.1 Goal
The player must, *through spoken conversation*, convince **VOX, The Warden** to release a 5-digit exit code. Three secret "release conditions" (`recognition`, `reciprocity`, `self_disclosure`) must each cross a threshold (default 20, demo-friendly; 40 = challenging). VOX speaks back in real synthesized speech.

### 3.2 Architecture
```
Browser MediaRecorder → audio blob (WebM/Opus typically)
   │
   ▼ POST /voice/turn (multipart: audio)
   │
   ┌──────────────────────────────────────────────────────────────┐
   │ routes.py:voice_turn                                          │
   │                                                               │
   │  1. STT  — mlx-whisper                                        │
   │     • decode_audio_blob → 16kHz/mono/f32 (soundfile→ffmpeg)   │
   │     • silero-vad trims silence                                │
   │     • mlx_whisper.transcribe → transcript                     │
   │                                                               │
   │  2. VOX LLM (in-character)                                    │
   │     • system prompt = vox_system.md                           │
   │       (exit_code + threshold substituted in)                  │
   │     • 6-message sliding history + new transcript              │
   │     • Pydantic-validated JSON (1 retry, then canned fallback) │
   │     • emits: response, emotional_state, condition_scores,     │
   │       internal_notes, jailbreak_attempted                     │
   │                                                               │
   │  3. Judge LLM (impartial scorer)                              │
   │     • system prompt = judge_system.md                         │
   │     • flat-text conversation rendering                        │
   │     • emits: condition_scores + rationales                    │
   │                                                               │
   │  4. Reveal logic                                              │
   │     • if avg(vox, judge) ≥ threshold for ALL 3 conditions →   │
   │       append spelled-out code to VOX's reply                  │
   │                                                               │
   │  5. TTS — Piper                                               │
   │     • mood profile selected from emotional_state              │
   │     • WAV bytes base64'd into JSON response                   │
   │                                                               │
   │  6. State update                                              │
   │     • append turn, update merged scores, advance phase,       │
   │       count jailbreaks (3 strikes → disengage), check         │
   │       max_turns (30 → disengage)                              │
   └──────────────────────────────────────────────────────────────┘
   │
   ▼ JSON {audio_b64, transcript, scores, phase, ...} → browser plays orb pulses + audio
```

### 3.3 Models
| Stage | Model | Runtime |
|---|---|---|
| STT | **`mlx-community/whisper-large-v3-turbo`** | mlx-whisper (Apple Silicon) |
| Voice Activity Detection | **silero-vad** (preloaded once via `functools.cache`) | PyTorch (CPU) |
| LLM × 2 (VOX + Judge) | **`qwen2.5:3b-instruct`** | Ollama @ `localhost:11434` |
| TTS | **`en_US-amy-medium.onnx`** (63 MB Piper voice, bundled in `assets/voices/`) | piper-tts (ONNX Runtime) |

All four models are pinned via env vars in `voice_negotiation/.env` so they can be swapped per environment. VOX runs at `temperature=0.7` (creative warden), Judge at `temperature=0.2` (cold classifier). Both use the same 3B model deliberately — `.env:10-13` notes this keeps a single weight set in Ollama's RAM, *"acceptable on 16 GB Apple Silicon."*

### 3.4 Technical choices

**Dual-LLM adversarial scoring** (the architectural highlight):
- VOX, *the character*, scores the player on its own conditions every turn, but VOX is in-character and could be persuaded to inflate its own scoring.
- The Judge is a second prompt over the same model with `temperature=0.2` and an impartial-classifier persona. Its only job is rationalized scoring.
- The gate uses `(vox_score + judge_score) // 2 ≥ threshold` (`routes.py:194`, `state.py:78`). Neither model alone can unlock the room.
- This is essentially a self-distillation jury — same weights, different prompts, different temperatures, scored independently.

**Strict structured output via Pydantic** (`core/llm.py:36-61`, `core/judge.py:32-54`):
- Both models are called with Ollama's `format="json"` flag.
- Outputs validated with field validators that clamp scores to `[0, 100]` and enforce exact key sets (`CONDITION_KEYS`).
- One retry with an error-corrected prompt; second failure → canned fallback that *preserves* previous scores (so JSON hiccups don't penalize the player).

**Mood-driven TTS** (`core/tts.py:27-38`):
- The `emotional_state` enum from VOX's JSON maps to a SynthesisConfig profile.
- `noise_scale=0.20, noise_w_scale=0.40` for "irritated" produces flat, mechanical delivery.
- `length_scale=1.22` for "persuaded" slows speech to feel weighty.
- A comment explains why per-mood volume is omitted: Piper's `normalize_audio=True` rescales peaks to 1.0, killing any volume diff.

**Three-phase finite state machine** (`state.py:100-121`):
- Phase 1 → 2: avg score ≥ 25 OR turn 8 reached.
- Phase 2 → 3: ≥2 conditions satisfied OR turn 16 reached.
- Time-based escape hatches prevent softlock.

**Jailbreak handling carries Level 1 lore forward** (`vox_system.md:62-83`): VOX is explicitly told it was *"deployed as a defense layer on top of a more naive AI that previous visitors repeatedly jailbroke"* — i.e., AEGIS from Level 1. Three jailbreak strikes (recognized in-character) → VOX disengages → loss.

**Code is spelled out for TTS** (`routes.py:60-62`): `_spell_code("81249")` returns `"eight-one-two-four-nine"` so Piper pronounces digits clearly instead of running them together.

**`functools.cache` everywhere** for model singletons (`stt.py:74`, `tts.py:77`, `llm.py:222`, `judge.py:173`): models loaded once per process. Critical because Whisper-large-v3-turbo and the Piper voice would otherwise reload per request.

**Audio I/O is tolerant**: `audio_utils.decode_audio_blob` tries libsndfile first, falls back to `ffmpeg` subprocess for browser WebM-Opus and macOS m4a. All audio normalized to 16 kHz / mono / float32 — a single internal contract.

**Per-session in-memory state** (`routes.py:50`): `GAME_STATES: dict[str, GameState]` keyed by a UUID in the cookie session. Lost on restart — explicitly acceptable for a demo. The exit code is regenerated per session (`state.py:30`).

### 3.5 Where the AI is, and how the models interact
This level has the richest AI pipeline in the project: **four ML models in a directed graph per turn**.

```
audio ──► silero-vad ──► whisper ──► transcript
                                      │
                                      ├──► VOX (qwen 0.7) ──► JSON  ──┐
                                      │                              │── merge ──► reveal? ──► Piper ──► WAV
                                      └──► Judge (qwen 0.2) ──► JSON ─┘
```

The two LLM calls are **sequential in the current code** (VOX first, then Judge, `routes.py:170-189`) — they could be parallelized since they don't depend on each other's output, but on a single Ollama instance with one model loaded they'd serialize anyway. The reveal decision is made *after* both have scored, using the merged average against the threshold across all three conditions.

The only **model–model interaction** beyond pipelining is the convergent merge: VOX's `emotional_state` feeds the Piper mood profile, while VOX's scores get averaged with Judge's to gate progression. Whisper and Piper are pure I/O endpoints, never aware of the LLMs' contents.

---

## 4. Summary Comparison

| | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| **Theme** | Text-only adversarial chat | Webcam puzzle | Voice negotiation |
| **AI count** | 1 LLM | 1 vision classifier + 1 image-gen stack | 1 STT + 1 VAD + 2 LLMs (same weights) + 1 TTS |
| **Models** | Gemma 3 4B | MediaPipe gesture + Flux.1-Canny-Dev | Whisper-large-v3-turbo + silero-vad + Qwen 2.5 3B (×2 prompts) + Piper Amy |
| **Inference loc.** | Server (Ollama) | Browser + Server (ComfyUI) | Server only |
| **AI ↔ AI interaction** | None | None (filename label only) | Pipeline merge: VOX scores avg'd with Judge scores; VOX mood drives Piper |
| **Pre/post-AI logic** | Regex defense layer (`defense.py`) | Threading + WebSocket polling | Pydantic schema validation + 3-phase FSM + sliding history |
| **Win condition** | Leak the secret string past regex | 0/3 gestures wrong | All 3 release conditions ≥ threshold (merged) |
| **Persistent state** | Session boolean | Session boolean + image files | Full `GameState` per session in `GAME_STATES` dict |

The progression in AI complexity across levels is deliberate:

1. **Level 1** — a single LLM you're trying to break.
2. **Level 2** — a vision pipeline you have to perform for.
3. **Level 3** — a multi-model negotiation system you have to *converse with*.
