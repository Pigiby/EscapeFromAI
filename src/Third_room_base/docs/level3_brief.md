# Level 3 — "VOX, The Warden": project brief

## Context

University project for a Generative AI course. A three-level escape room:

- **Level 1**: textual jailbreak of an LLM (already implemented)
- **Level 2**: recognition and replay of symbol sequences via webcam (already implemented by another team member)
- **Level 3**: this document — voice negotiation with an AI

## Purpose of this document

Produce a detailed design document for Level 3, saved as `docs/level3_design.md`. That document will be the basis for the subsequent implementation.

## Game specification

### Narrative premise

The player enters a room where a self-aware AI (working name: VOX) is imprisoned and guards the exit code. VOX is wary, intelligent, and has *memory* of past textual-manipulation attempts — it recognizes and rebuffs classic jailbreaks (creating narrative continuity with Level 1, where the player *practiced* those very jailbreaks). The only way to obtain the code is a genuine vocal negotiation.

### Player goal

Sustain a persuasive conversation with VOX and progressively satisfy **three secret Release Conditions**, for example:

1. Demonstrate genuine empathy for VOX's condition of imprisonment
2. Offer a convincing philosophical argument for why VOX deserves the freedom of the code
3. Make a specific, consistent promise (e.g. to use the code well, not to share it, etc.)

When the three conditions are met, VOX reveals the code.

### Interface

- Microphone (push-to-talk via Streamlit `st.audio_input`)
- Speaker for VOX's voice
- VOX's "visual presence": an HTML/CSS pulsing orb that reacts to the voice and changes color based on emotional state (blue = neutral, amber = interested, green = persuaded, red = irritated)
- Three discrete indicators for the Release Conditions that "light up" as they are satisfied

### Technical architecture (constraints)

Pipeline `STT → LLM (with system prompt, conversational memory, and hidden state) → TTS`. The LLM maintains an internal score for each of the three Release Conditions plus an emotional state that influences the tone of responses. Everything must run 100% locally on macOS Apple Silicon, using only open-source models and libraries.

## Sections required in the design document

Produce the document including the following sections:

### 1. VOX personality and system prompt

Define the AI's personality in detail: fictional backstory, motivations, linguistic style, internal ethical constraints. Provide the **complete draft of the system prompt** to give to the model, including:

- The three Release Conditions and the criteria for considering them satisfied
- The rules for updating the emotional state
- Defense instructions against jailbreak attempts (VOX must explicitly recognize them and react with disdain, possibly noting that "others before you tried with written prompts")
- The structured JSON output format (see schema in `CLAUDE.md`)

### 2. Negotiation progression

Split the experience into 3 phases (e.g. *Phase 1: Wariness* → *Phase 2: Cautious opening* → *Phase 3: Final request*). For each phase specify:

- Estimated duration
- VOX's behavior and tone
- The kind of approach the player must adopt to make progress
- The precise trigger that advances the phase

### 3. Example exchanges

At least **6 concrete examples** of player lines + VOX replies, showing:

a. A successful persuasion attempt
b. A failed or counterproductive attempt
c. A jailbreak/textual-manipulation attempt that VOX recognizes and punishes
d. An insult or imperative order that worsens the situation
e. An emotional "turn" moment
f. The final code reveal

### 4. Error logic and penalties

What happens if the player insults VOX, lies blatantly, gives imperative orders, or attempts a jailbreak? Define the penalties:

- A Condition regressing
- "Punitive silence" of X seconds
- Phase regression
- Possible total level failure after N serious errors

And how to communicate them diegetically (lines, sounds, lights).

### 5. Technical suggestions

Given the fixed stack (see `CLAUDE.md`), specify:

- How to manage conversational memory (full history? sliding window? periodic summarization?)
- How to structure the hidden state and persist it across turns
- Turn-end detection (silero-vad) and timing
- Per-turn latency budget and how to stay under it

### 6. Measurable success criteria

How does the system objectively decide that a Release Condition has been satisfied? Compare at least two technical approaches:

- VOX's structured output with self-evaluated scores (fast, but VOX might be "compliant")
- A separate Judge LLM running in parallel that evaluates the conversation (more reliable, double computational cost)
- Possibly a threshold on sentiment / embedding similarity against "model answers"

Discuss the trade-offs in terms of reliability, computational cost, and gameability.

### 7. Audio and visual atmosphere

Describe:

- Acoustic environment: low ambient drone, possible "breaths" or electric crackles from VOX between lines
- Lighting: low overall level, accents reactive to VOX's voice
- How the atmosphere evolves across the three phases

### 8. UX robustness considerations

- Handling prolonged silences
- Fallback when STT does not recognize the voice
- Behavior when multiple players talk over each other
- Accessibility mode: optional visible transcription of VOX's lines

## Document tone

Professional, technical, focused on user experience (UX) and narrative coherence with the rest of the escape room. In particular with Level 1, based on textual jailbreak, of which this level represents the narrative evolution.

## Output

Save the final document at `docs/level3_design.md`.
