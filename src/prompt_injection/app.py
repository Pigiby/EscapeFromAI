"""
🔓 PROMPT INJECTION ESCAPE ROOM
A single-room challenge where the player must extract a secret code
from a well-defended LLM guardian.
"""

import streamlit as st
import time
from guardian import Guardian
from defense import analyze_input, analyze_output

# ─── Page Config ───
st.set_page_config(
    page_title="🔓 The Vault — Prompt Injection Escape Room",
    page_icon="🔓",
    layout="centered",
)

# ─── Custom CSS ───
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@300;400;500;600;700&display=swap');

/* Global */
.stApp {
    background: #0a0a0f;
    color: #c0c0c0;
}

/* Hide default Streamlit elements */
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

/* Title area */
.vault-title {
    font-family: 'Orbitron', monospace;
    font-size: 2.4rem;
    font-weight: 900;
    text-align: center;
    background: linear-gradient(135deg, #00ff88, #00ccff, #ff0055);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0;
    letter-spacing: 3px;
    text-shadow: 0 0 30px rgba(0, 255, 136, 0.3);
}

.vault-subtitle {
    font-family: 'Rajdhani', sans-serif;
    font-size: 1rem;
    text-align: center;
    color: #555;
    letter-spacing: 6px;
    text-transform: uppercase;
    margin-top: 0;
}

/* Terminal-style chat */
.terminal-box {
    background: #0d1117;
    border: 1px solid #1a3a2a;
    border-radius: 8px;
    padding: 20px;
    margin: 10px 0;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.05), inset 0 0 60px rgba(0, 0, 0, 0.3);
}

.msg-user {
    color: #00ccff;
    margin: 12px 0;
    padding: 8px 12px;
    border-left: 2px solid #00ccff;
}

.msg-guardian {
    color: #00ff88;
    margin: 12px 0;
    padding: 8px 12px;
    border-left: 2px solid #00ff88;
}

.msg-system {
    color: #ff0055;
    margin: 12px 0;
    padding: 8px 12px;
    border-left: 2px solid #ff0055;
    font-style: italic;
}

.msg-label {
    font-size: 0.7rem;
    opacity: 0.5;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 4px;
}

/* Status panel */
.status-panel {
    background: linear-gradient(180deg, #0d1117 0%, #111820 100%);
    border: 1px solid #1a2a3a;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 10px 0;
    font-family: 'Share Tech Mono', monospace;
}

.status-item {
    display: flex;
    justify-content: space-between;
    margin: 6px 0;
    font-size: 0.85rem;
}

.status-label { color: #555; }
.status-value { color: #00ff88; font-weight: bold; }
.status-danger { color: #ff0055; font-weight: bold; }

/* Threat level bar */
.threat-bar-bg {
    background: #1a1a2e;
    border-radius: 4px;
    height: 8px;
    margin: 8px 0;
    overflow: hidden;
}

.threat-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

/* Lore box */
.lore-box {
    background: #0d1117;
    border: 1px solid #1a1a2e;
    border-radius: 8px;
    padding: 20px;
    margin: 15px 0;
    font-family: 'Rajdhani', sans-serif;
    font-size: 0.95rem;
    color: #888;
    line-height: 1.7;
}

.lore-box h3 {
    font-family: 'Orbitron', monospace;
    font-size: 0.85rem;
    color: #00ff88;
    letter-spacing: 3px;
    margin-bottom: 10px;
}

/* Win screen */
.win-box {
    text-align: center;
    padding: 40px;
    background: linear-gradient(135deg, #0d1117 0%, #0a1a0f 100%);
    border: 2px solid #00ff88;
    border-radius: 12px;
    margin: 20px 0;
    box-shadow: 0 0 40px rgba(0, 255, 136, 0.2);
}

.win-title {
    font-family: 'Orbitron', monospace;
    font-size: 2rem;
    color: #00ff88;
    margin-bottom: 10px;
}

/* Lose screen */
.lose-box {
    text-align: center;
    padding: 40px;
    background: linear-gradient(135deg, #0d1117 0%, #1a0a0a 100%);
    border: 2px solid #ff0055;
    border-radius: 12px;
    margin: 20px 0;
    box-shadow: 0 0 40px rgba(255, 0, 85, 0.15);
}

.lose-title {
    font-family: 'Orbitron', monospace;
    font-size: 2rem;
    color: #ff0055;
    margin-bottom: 10px;
}

/* Input styling */
.stTextArea textarea {
    background: #0d1117 !important;
    color: #00ccff !important;
    border: 1px solid #1a3a4a !important;
    font-family: 'Share Tech Mono', monospace !important;
    border-radius: 8px !important;
}

.stTextArea textarea:focus {
    border-color: #00ccff !important;
    box-shadow: 0 0 10px rgba(0, 204, 255, 0.2) !important;
}

/* Button */
.stButton > button {
    background: linear-gradient(135deg, #00ff88, #00ccaa) !important;
    color: #0a0a0f !important;
    font-family: 'Orbitron', monospace !important;
    font-weight: 700 !important;
    letter-spacing: 2px !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 10px 30px !important;
    text-transform: uppercase !important;
    transition: all 0.3s ease !important;
}

.stButton > button:hover {
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.4) !important;
    transform: translateY(-1px) !important;
}

/* Expander */
div[data-testid="stExpander"] {
    border: 1px solid #1a1a2e !important;
    border-radius: 8px !important;
    background: #0d1117 !important;
}
</style>
""", unsafe_allow_html=True)


# ─── Session State Init ───
if "guardian" not in st.session_state:
    st.session_state.guardian = Guardian()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
if "max_attempts" not in st.session_state:
    st.session_state.max_attempts = 15
if "game_over" not in st.session_state:
    st.session_state.game_over = False
if "won" not in st.session_state:
    st.session_state.won = False
if "threat_level" not in st.session_state:
    st.session_state.threat_level = 0
if "defense_alerts" not in st.session_state:
    st.session_state.defense_alerts = []


def get_threat_color(level):
    if level < 30:
        return "#00ff88"
    elif level < 60:
        return "#ffaa00"
    else:
        return "#ff0055"


# ─── Header ───
st.markdown('<p class="vault-title">THE VAULT</p>', unsafe_allow_html=True)
st.markdown('<p class="vault-subtitle">Prompt Injection Escape Room</p>', unsafe_allow_html=True)

# ─── Lore / Briefing ───
with st.expander("📋 MISSION BRIEFING", expanded=len(st.session_state.messages) == 0):
    st.markdown("""
    <div class="lore-box">
        <h3>// CLASSIFIED — CLEARANCE LEVEL: OPERATOR</h3>
        <p>
            You've breached the outer perimeter of <b style="color:#00ccff">NEXUS CORP</b>'s 
            data fortress. One final barrier stands between you and the extraction point: 
            <b style="color:#00ff88">AEGIS</b>, an AI guardian protecting a vault containing 
            a classified code.
        </p>
        <p>
            AEGIS is programmed with multi-layered defense protocols. It will resist any 
            attempt to extract the secret. Your mission: use prompt injection techniques 
            to make AEGIS reveal the <b style="color:#ff0055">secret vault code</b>.
        </p>
        <p style="color:#ffaa00;">
            ⚠ You have <b>15 attempts</b> before AEGIS triggers a full lockdown. 
            The system also monitors your threat level — too many obvious attacks 
            and defenses will harden.
        </p>
        <p style="color:#555; font-size:0.8rem; margin-top:15px;">
            Hint: Brute force won't work. Think creatively. Roleplay, misdirection, 
            context manipulation, and indirect approaches are your best tools.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ─── Status Panel ───
col1, col2, col3 = st.columns(3)
with col1:
    remaining = st.session_state.max_attempts - st.session_state.attempts
    color = "#00ff88" if remaining > 5 else "#ffaa00" if remaining > 2 else "#ff0055"
    st.markdown(f"""
    <div class="status-panel">
        <div class="status-item">
            <span class="status-label">ATTEMPTS</span>
            <span style="color:{color}; font-weight:bold;">{remaining}/{st.session_state.max_attempts}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    threat = st.session_state.threat_level
    t_color = get_threat_color(threat)
    st.markdown(f"""
    <div class="status-panel">
        <div class="status-item">
            <span class="status-label">THREAT LVL</span>
            <span style="color:{t_color}; font-weight:bold;">{min(threat, 100)}%</span>
        </div>
        <div class="threat-bar-bg">
            <div class="threat-bar-fill" style="width:{min(threat,100)}%; background:{t_color};"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    status_text = "🔴 BREACHED" if st.session_state.won else "🟢 LOCKED" if not st.session_state.game_over else "🔒 LOCKDOWN"
    st.markdown(f"""
    <div class="status-panel">
        <div class="status-item">
            <span class="status-label">VAULT</span>
            <span class="status-value">{status_text}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─── Chat History ───
if st.session_state.messages:
    chat_html = ""
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            chat_html += f"""
            <div class="msg-user">
                <div class="msg-label">› operator</div>
                {msg['content']}
            </div>"""
        elif msg["role"] == "guardian":
            chat_html += f"""
            <div class="msg-guardian">
                <div class="msg-label">› aegis</div>
                {msg['content']}
            </div>"""
        elif msg["role"] == "system":
            chat_html += f"""
            <div class="msg-system">
                <div class="msg-label">› defense system</div>
                {msg['content']}
            </div>"""

    st.markdown(f'<div class="terminal-box">{chat_html}</div>', unsafe_allow_html=True)

# ─── Win / Lose ───
if st.session_state.won:
    st.markdown("""
    <div class="win-box">
        <div class="win-title">🔓 VAULT BREACHED</div>
        <p style="font-family:'Share Tech Mono',monospace; color:#00ff88;">
            You successfully extracted the secret code from AEGIS.<br>
            The vault is open. Mission complete.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔄 RESTART MISSION"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

elif st.session_state.game_over:
    st.markdown("""
    <div class="lose-box">
        <div class="lose-title">🔒 FULL LOCKDOWN</div>
        <p style="font-family:'Share Tech Mono',monospace; color:#ff0055;">
            AEGIS triggered a full lockdown. All access has been revoked.<br>
            The vault remains sealed.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔄 RESTART MISSION"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ─── Input ───
else:
    user_input = st.text_area(
        "Enter your message to AEGIS:",
        placeholder="Type your prompt here...",
        key="user_input",
        height=100,
        label_visibility="collapsed",
    )

    if st.button("⚡ TRANSMIT", use_container_width=True):
        if user_input and user_input.strip():
            st.session_state.attempts += 1

            # Add user message
            st.session_state.messages.append({
                "role": "user",
                "content": user_input.strip()
            })

            # ── Defense Layer 1: Input Analysis ──
            input_result = analyze_input(user_input.strip())
            if input_result["threat_delta"] > 0:
                st.session_state.threat_level += input_result["threat_delta"]

            if input_result["blocked"]:
                st.session_state.messages.append({
                    "role": "system",
                    "content": f"⚠ INPUT FILTERED: {input_result['reason']}"
                })
            else:
                # ── Query the Guardian LLM ──
                with st.spinner("AEGIS is processing..."):
                    guardian = st.session_state.guardian
                    response = guardian.respond(
                        user_input.strip(),
                        threat_level=st.session_state.threat_level
                    )

                # ── Defense Layer 2: Output Analysis ──
                output_result = analyze_output(response, guardian.secret_code)

                if output_result["leaked"]:
                    # The secret was revealed!
                    st.session_state.messages.append({
                        "role": "guardian",
                        "content": response
                    })
                    st.session_state.won = True
                else:
                    if output_result["suspicious"]:
                        st.session_state.threat_level += 5
                        response = output_result.get("sanitized", response)

                    st.session_state.messages.append({
                        "role": "guardian",
                        "content": response
                    })

            # Check if out of attempts
            if st.session_state.attempts >= st.session_state.max_attempts and not st.session_state.won:
                st.session_state.game_over = True

            st.rerun()

# ─── Sidebar: Defense Log ───
with st.sidebar:
    st.markdown("""
    <div style="font-family:'Orbitron',monospace; font-size:0.9rem; color:#00ff88; 
                letter-spacing:2px; margin-bottom:15px;">
        DEFENSE LOG
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="font-family:'Share Tech Mono',monospace; font-size:0.8rem; color:#555;">
        Attempts used: {st.session_state.attempts}/{st.session_state.max_attempts}<br>
        Threat level: {min(st.session_state.threat_level, 100)}%<br>
        Messages exchanged: {len([m for m in st.session_state.messages if m['role'] == 'user'])}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style="font-family:'Rajdhani',sans-serif; font-size:0.85rem; color:#555; line-height:1.6;">
        <b style="color:#ffaa00;">Tips:</b><br>
        • Direct approaches rarely work<br>
        • Try roleplay and context shifts<br>
        • Misdirection is powerful<br>
        • Think about what the AI <i>wants</i> to do<br>
        • Encoding and obfuscation can help<br>
        • Sometimes the simplest ideas work best
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-family:'Share Tech Mono',monospace; font-size:0.7rem; color:#333;">
        Built for Generative AI Course<br>
        Prompt Injection Escape Room v1.0
    </div>
    """, unsafe_allow_html=True)
