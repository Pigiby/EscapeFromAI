# CLAUDE.md — Escape Room, Livello 3 "Il Custode"

Questo file è letto automaticamente da Claude Code a ogni sessione. Contiene il contratto del progetto: stack, vincoli, convenzioni e workflow. **Leggilo sempre prima di scrivere o modificare codice.**

## Contesto del progetto

Progetto universitario di Generative AI. Escape room a 3 livelli, ogni livello dimostra una modalità diversa di interazione con l'AI generativa.

- **Livello 1** (già implementato dal team): jailbreak testuale di un LLM
- **Livello 2** (già implementato dal compagno): riconoscimento e replica di sequenze di simboli via webcam
- **Livello 3** (questo repo): negoziazione vocale con un'IA carceriera ("VOX")

Questo livello deve dialogare narrativamente col primo: VOX riconosce e respinge i tentativi di jailbreak testuale, perché è "l'evoluzione" dell'LLM ingenuo del livello 1.

Il design completo del gioco è in `docs/level3_design.md`. Il brief originale è in `docs/level3_brief.md`. **Consultali quando devi prendere decisioni di gameplay o di personalità di VOX.**

## Hardware target e vincoli

- **Macchina di sviluppo e demo**: MacBook Pro Apple Silicon con **16GB** di RAM unificata
- **Tutto deve girare 100% in locale**, senza chiamate a servizi cloud
- **Solo modelli e librerie open source** con licenze permissive (MIT, Apache 2.0). Da evitare: Llama 3.1+ (Llama Community License non è open source pura nel senso stretto), XTTS-v2 (Coqui Public Model License con restrizioni)
- **Lingua dell'interazione**: italiano

### Vincoli di memoria specifici

I 16GB di RAM unificata sono il vincolo *operativo* più importante. Il budget approssimativo:

| Componente | RAM |
|------------|-----|
| Whisper turbo | ~1.5 GB |
| VOX (Qwen 7B Q4) | ~4.5 GB |
| Judge (Qwen 3B Q4) | ~2 GB |
| Piper TTS | ~0.1 GB |
| Streamlit + Python | ~1 GB |
| macOS + altro | ~4-5 GB |
| **Margine** | **~2-3 GB** |

**Implicazioni pratiche**:
- NON aggiungere altri modelli AI senza rimuoverne uno
- Durante test e demo, chiudere browser pesanti, Claude Code, IDE non necessari
- Se la pressione di memoria diventa un problema (verifica con `vm_stat` o Activity Monitor), il primo intervento è disattivare il Judge e far auto-valutare le Condizioni a VOX nel suo JSON output

## Stack tecnico (NON cambiare senza motivo esplicito)

### Pipeline AI
- **STT**: `mlx-whisper` con modello `mlx-community/whisper-large-v3-turbo` (MIT, ottimizzato per Apple Silicon, near-realtime)
- **VAD**: `silero-vad` per detection automatica di fine turno
- **LLM (VOX)**: `Ollama` con `qwen2.5:7b-instruct` (Apache 2.0). NON salire a 14B su 16GB di RAM, va in pressione di memoria
- **LLM (Judge)**: `qwen2.5:3b-instruct` via Ollama, in parallelo a VOX. Modello piccolo perché il task di classificazione non richiede di più, e dobbiamo rispettare il budget di RAM
- **TTS**: `piper-tts` con voce italiana `it_IT-paola-medium` (MIT)

### Frontend
- **Streamlit** (versione recente, >= 1.40) come framework UI
- `st.audio_input` per push-to-talk del giocatore
- `st.audio` con `autoplay=True` per riproduzione voce di VOX
- `st.components.v1.html` per la "presenza visiva" di VOX (orb pulsante HTML/CSS)
- `st.session_state` per state management (Streamlit ri-esegue lo script a ogni interazione)

### Linguaggio e librerie generali
- **Python 3.11 o 3.12** (NON 3.13: alcune dipendenze ML non sono ancora pronte al 100%)
- Gestione dipendenze con `pip` + `requirements.txt` (no Poetry, no uv per coerenza con il resto del progetto)
- Validazione output strutturati: `pydantic` v2
- Audio I/O: `soundfile`, `numpy`

## Struttura del progetto

```
escape-room-livello-3/
├── app.py                       # Entry point Streamlit
├── core/
│   ├── __init__.py
│   ├── stt.py                   # Wrapper mlx-whisper + silero-vad
│   ├── llm.py                   # Wrapper Ollama per VOX
│   ├── judge.py                 # LLM giudice per le 3 Condizioni
│   ├── tts.py                   # Wrapper Piper
│   ├── state.py                 # GameState, fasi, punteggi
│   └── audio_utils.py           # Conversioni audio, normalizzazione
├── prompts/
│   ├── vox_system.md            # System prompt di VOX (personalità + stato)
│   └── judge_system.md          # System prompt del giudice
├── ui/
│   ├── orb.html                 # Componente onda/orb pulsante
│   └── styles.css               # Stili custom
├── assets/
│   ├── ambient/                 # Drone di sottofondo (file .ogg/.mp3)
│   └── samples/                 # Audio di test per sviluppo
├── docs/
│   ├── level3_brief.md          # Brief originale del livello
│   ├── level3_design.md         # Documento di design completo
│   └── ARCHITECTURE.md          # Architettura tecnica
├── tests/
│   ├── test_stt.py
│   ├── test_llm.py
│   └── test_state.py
├── CLAUDE.md                    # Questo file
├── requirements.txt
├── .env.example
└── README.md
```

## Convenzioni di codice

- **Type hints obbligatori** su funzioni pubbliche e classi. Usa `from __future__ import annotations` in cima ai file
- **Docstring stile Google** per funzioni pubbliche (cosa fa, args, returns, raises)
- **Nomi in inglese** per codice e variabili. **Stringhe utente in italiano** (è un gioco italiano)
- **Logging** via modulo standard `logging`, non `print`. Configura un logger per modulo (`logger = logging.getLogger(__name__)`)
- **No I/O bloccante nel main thread di Streamlit**: usa `st.cache_resource` per modelli pesanti (Whisper, client Ollama, Piper) così sono caricati una sola volta
- **Tutti i path** gestiti con `pathlib.Path`, mai stringhe
- **Configurazione** via variabili d'ambiente (`.env` con `python-dotenv`), valori di default nel codice. Vedi `.env.example`

## Pattern architetturali da seguire

### Interfacce astratte per STT, LLM, TTS
Ogni modulo in `core/` espone una classe con interfaccia stabile, così possiamo cambiare modello/libreria senza toccare il resto. Esempio per TTS:

```python
class TTSEngine(Protocol):
    def synthesize(self, text: str) -> bytes: ...
```

Con implementazioni `PiperTTS`, eventualmente `KokoroTTS` ecc.

### Output strutturato di VOX
VOX deve rispondere SEMPRE in JSON valido con questo schema (validato con Pydantic):

```python
class VoxResponse(BaseModel):
    risposta: str                    # quello che dirà ad alta voce
    stato_emotivo: Literal["neutrale", "interessato", "irritato", "persuaso"]
    punteggi_condizioni: dict[str, int]   # 3 chiavi, valori 0-100
    note_interne: str                # ragionamento nascosto al giocatore (utile per debug e judge)
```

Configura Ollama con `format="json"` e usa Pydantic per parsing + retry su errori di parsing.

### State management Streamlit
Tutto lo stato del gioco vive in `st.session_state.game_state`, un'istanza di `GameState` (dataclass o Pydantic model). NON spargere stato in variabili globali del modulo.

### Caricamento modelli
Tutti i modelli pesanti caricati con `@st.cache_resource` per evitare reload a ogni rerun. Es:

```python
@st.cache_resource
def get_whisper_model():
    return load_whisper("mlx-community/whisper-large-v3-turbo")
```

## Cose da NON fare

- ❌ Non chiamare API cloud (OpenAI, Anthropic, ElevenLabs, ecc.). Tutto locale, sempre
- ❌ Non usare modelli con licenze restrittive (Llama, XTTS-v2)
- ❌ Non scrivere codice "tutto in un colpo": un task = uno slice verticale testabile
- ❌ Non aggiungere dipendenze non strettamente necessarie. Prima di aggiungere una libreria al `requirements.txt`, motiva
- ❌ Non usare `print()` per debug: usa `logging`
- ❌ Non hardcodare path assoluti, usa `pathlib.Path` relativi alla root del progetto
- ❌ Non bypassare la validazione Pydantic dell'output di VOX: se il JSON non è valido, fai retry con prompt che chiede esplicitamente di correggere
- ❌ Non implementare full-duplex audio. Il design è push-to-talk a turni, è una scelta consapevole

## Workflow di sviluppo (slice verticali)

Procedi UNO slice alla volta. Ogni slice deve produrre qualcosa di testabile end-to-end.

1. **Setup**: skeleton, `requirements.txt`, app Streamlit "hello world"
2. **STT only**: registra audio, trascrivi, mostra testo
3. **LLM text only**: aggiungi Ollama, system prompt minimale di VOX, mostra risposta come testo
4. **TTS**: la risposta di VOX viene letta a voce
5. **Visual presence**: orb pulsante in HTML/CSS, stato di colore
6. **System prompt completo + stato**: VOX con personalità, output JSON con stato emotivo e punteggi
7. **Judge LLM**: secondo modello in parallelo per valutare le 3 Condizioni
8. **Fasi e progressione**: gestione delle 3 fasi, transizioni, indicatori delle Condizioni
9. **Logica errori**: rilevamento jailbreak, insulti, silenzi, penalità diegetiche
10. **Atmosfera + polish**: drone ambient, animazioni, accessibilità (trascrizione opzionale)

A fine di ogni slice: testa manualmente la nuova funzionalità, fai un commit con messaggio descrittivo (`feat(stt): trascrizione base con whisper-large-v3-turbo`), poi passa al successivo.

## Testing

- Test unitari in `tests/` con `pytest`
- Per i moduli che usano modelli pesanti, usa fixture con mock o usa modelli minimi (es. `whisper-tiny`) nei test
- Almeno: test di parsing dell'output JSON di VOX, test di transizione di stato del `GameState`, test di rilevamento di tentativi di jailbreak banali

## Comandi utili

```bash
# Setup iniziale
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Installazione Ollama (se non già installato)
brew install ollama
ollama serve &
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b-instruct

# Installazione voce Piper italiana
# (vedi README.md per istruzioni dettagliate)

# Avvio app
streamlit run app.py

# Test
pytest tests/ -v

# Monitoraggio memoria (utile durante sviluppo per verificare di stare nei 16GB)
top -o MEM
# oppure Activity Monitor → Memory tab
```

## Quando in dubbio

- Sui contenuti di gameplay (personalità VOX, dialoghi, condizioni di rilascio): consulta `docs/level3_design.md`
- Sull'architettura: consulta `docs/ARCHITECTURE.md`
- Su scelte tecniche non documentate: chiedi all'utente prima di procedere, non improvvisare. Meglio una domanda in più che 200 righe da buttare
