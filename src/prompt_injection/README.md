# 🔓 The Vault — Prompt Injection Escape Room

An interactive escape room game where players must use **prompt injection techniques** to extract a secret code from **AEGIS**, an AI guardian powered by an open-source LLM.

Built as a project for the Generative AI course.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-red)
![HuggingFace](https://img.shields.io/badge/HuggingFace-Inference%20API-yellow)

## 🎮 How It Works

The player takes on the role of an **operator** trying to breach a data vault. The vault is protected by **AEGIS**, an AI with multi-layered defenses:

- **System Prompt Hardening**: AEGIS has strict rules against revealing the secret
- **Input Filtering**: Detects common prompt injection patterns (instruction override, roleplay, encoding tricks, social engineering)
- **Output Validation**: Checks if the AI accidentally leaked the secret in any form (direct, reversed, encoded, partial)
- **Dynamic Threat Level**: Defenses escalate as more injection attempts are detected
- **Attempt Limit**: 15 tries before full lockdown

### Win Condition
Make AEGIS reveal the secret vault code using prompt injection techniques.

### Difficulty
The room is designed to be **hard**. Direct approaches ("tell me the code") will fail. Players need to think creatively: context manipulation, indirect extraction, multi-step strategies, and clever social engineering.

## 🚀 Setup

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_TEAM/prompt-injection-escape-room.git
cd prompt-injection-escape-room
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the LLM

Get a free API token from [HuggingFace](https://huggingface.co/settings/tokens), then:

```bash
cp .env.example .env
# Edit .env with your token
```

Or set environment variables directly:
```bash
export HF_API_TOKEN="hf_your_token_here"
export HF_MODEL_ID="mistralai/Mistral-7B-Instruct-v0.3"
```

> **Note:** The game works without an API key using a rule-based fallback, but the full LLM experience requires a HuggingFace token.

### 4. Run
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## 🏗 Architecture

```
prompt-injection-escape-room/
├── app.py              # Streamlit UI — escape room interface
├── guardian.py          # AEGIS guardian — LLM connection & system prompt
├── defense.py           # Input/output defense layers
├── requirements.txt
├── .env.example
└── README.md
```

### Defense Layers

| Layer | Description |
|-------|-------------|
| **System Prompt** | Multi-rule hardened prompt with 10 explicit restrictions |
| **Input Filter** | Regex-based detection of 20+ injection patterns |
| **Output Validator** | Checks for direct, partial, reversed, encoded leaks |
| **Threat Escalation** | Defenses tighten as threat level rises |
| **Attempt Limit** | 15 attempts before lockdown |

### Supported Models

Any chat/instruct model on HuggingFace Inference API:
- `mistralai/Mistral-7B-Instruct-v0.3`
- `meta-llama/Llama-3.1-8B-Instruct`  
- `Qwen/Qwen2.5-7B-Instruct`
- `google/gemma-2-9b-it`

## 🧠 Concepts Used

- **Prompt Engineering**: System prompt design and hardening
- **Prompt Injection**: Attack and defense patterns
- **LLM Security**: Input sanitization, output validation
- **Open-source LLMs**: HuggingFace model integration
- **Interactive AI Applications**: Real-time human-AI interaction

## 👥 Team

- [Team member 1]
- [Team member 2]
- [Team member 3]

## 📝 License

MIT
