# Architettura Tecnica — Livello 3 "Il Custode"

> Questo documento descrive l'architettura tecnica del sistema, complementare a `level3_design.md` (che descrive il gameplay).

## Diagramma a blocchi

```
┌────────────────┐   audio    ┌─────────────────┐   testo it    ┌───────────────┐
│  st.audio_input │──────────▶│  silero-vad +   │──────────────▶│   VOX (LLM)   │
│  (Streamlit)   │            │  mlx-whisper    │               │  qwen2.5:14b  │
└────────────────┘            │   (large-v3-    │               │   via Ollama  │
                              │    turbo)       │               └───────┬───────┘
                                                                        │
                              ┌─────────────────┐                       │ JSON
                              │   GameState     │◀──────────────────────┤
                              │ (st.session_    │      stato +          │
                              │   state)        │      punteggi         │
                              └────────┬────────┘                       │
                                       │                                │
                                       │            in parallelo        ▼
                              ┌────────▼────────┐               ┌───────────────┐
                              │   UI updates    │               │  Judge (LLM)  │
                              │  (orb, fasi,    │◀──────────────│  qwen2.5:7b   │
                              │   condizioni)   │   verifica    │  via Ollama   │
                              └─────────────────┘   condizioni  └───────────────┘
                                       │
                                       │ testo risposta VOX
                                       ▼
                              ┌─────────────────┐               ┌───────────────┐
                              │  Piper TTS      │──────────────▶│   st.audio    │
                              │  (it_IT-paola-  │     wav       │   autoplay    │
                              │     medium)     │               └───────────────┘
                              └─────────────────┘
```

## Flusso di un turno

1. **Cattura audio**: il giocatore preme il pulsante in `st.audio_input` e parla
2. **VAD + STT** (~1s): silero-vad isola la parte vocale, mlx-whisper trascrive in italiano
3. **VOX inference** (~3-5s): la trascrizione + history + system prompt vanno a Ollama; risposta in JSON validato con Pydantic
4. **Judge in parallelo** (~2-3s): la stessa conversazione (più la nuova battuta) va al modello giudice che valuta indipendentemente le 3 Condizioni
5. **State update**: i punteggi di VOX e Judge vengono fusi (es. media pesata), il `GameState` viene aggiornato, eventuali transizioni di fase vengono attivate
6. **TTS** (~1s): il campo `risposta` del JSON viene sintetizzato da Piper
7. **UI update**: orb cambia colore in base a `stato_emotivo`, indicatori delle Condizioni si aggiornano, audio di VOX viene riprodotto in autoplay
8. **Loop**: il giocatore può registrare di nuovo

**Latenza totale stimata per turno**: 5-8 secondi tra fine voce giocatore e inizio voce VOX.

## Decisioni architetturali

### Perché push-to-talk e non full-duplex

Il full-duplex (interruzioni, sovrapposizioni) è tecnicamente complesso (richiede streaming STT, gestione barge-in, echo cancellation) e poco compatibile con Streamlit. Per un'escape room dove ogni risposta richiede *riflessione* dal giocatore, il push-to-talk è anche narrativamente più appropriato.

### Perché due LLM (VOX + Judge) e non uno solo

Affidare a VOX stesso la valutazione delle Condizioni è un single-point-of-failure: VOX ha incentivo a "voler dialogare" e potrebbe essere troppo compiacente, oppure al contrario troppo severo per protagonismo narrativo. Un Judge separato, freddo, con system prompt focalizzato solo sulla classificazione, riduce questi bias.

Il costo è ~2GB di RAM e ~1-2s di inference extra per turno, mitigato eseguendo il Judge in parallelo a VOX. Su 16GB sta nel budget, ma è la prima cosa da rimuovere se la pressione di memoria diventa critica.

### Perché Ollama e non `mlx-lm` diretto

`mlx-lm` darebbe latenza più bassa (no overhead HTTP), ma:
- Ollama gestisce automaticamente lifecycle dei modelli, quantizzazione, swap
- API HTTP è più semplice da debuggare
- Supporto nativo per JSON mode (`format="json"`)
- Possibilità di sostituire il modello senza toccare il codice

Se in fase di profiling la latenza di Ollama dovesse essere il bottleneck, valutare `mlx-lm` come alternativa.

### Gestione della memoria conversazionale

**Approccio**: full history fino a un budget di token (es. 8K), oltre il quale si fa **sliding window** mantenendo:
- Sempre il system prompt
- Sempre i primi 2-3 turni (set-up della trattativa)
- Gli ultimi N turni che stanno nel budget

Alternativa più sofisticata (da valutare in fase 7): riassunto periodico generato dal modello stesso ogni 6-8 turni. Più complesso ma scala meglio se il giocatore è prolisso.

### Validazione dell'output JSON di VOX

Ollama ha `format="json"` ma non garantisce aderenza a uno schema specifico. Strategia:

1. Chiamata a Ollama con `format="json"` e schema esplicitato nel system prompt
2. Parsing con `pydantic.BaseModel.model_validate_json()`
3. Su `ValidationError`: log dell'errore + retry con prompt di correzione (max 1 retry)
4. Su secondo fallimento: fallback a una risposta canned (es. VOX "ha un crash momentaneo, attenda"), senza far crashare il gioco

## Considerazioni di performance

| Componente | Modello | RAM | Latenza tipica |
|------------|---------|-----|----------------|
| STT | whisper-large-v3-turbo (MLX) | ~1.5 GB | ~1s per 5s di audio |
| VOX | qwen2.5:7b (Q4_K_M) | ~4.5 GB | ~3-5s per 200 token |
| Judge | qwen2.5:3b (Q4_K_M) | ~2 GB | ~1-2s per 100 token |
| TTS | piper paola-medium | ~70 MB | <1s per frase |
| **Totale modelli** | | **~8 GB** | **5-8s/turno** |

Su 16GB di RAM unificata, dopo aver tolto macOS (~4-5GB), Streamlit + Python (~1GB) e i modelli (~8GB), restano ~2-3GB di margine. È sufficiente per un funzionamento stabile, ma non c'è spazio per modelli più grandi.

### Strategie di degrado se la pressione di memoria è eccessiva

In ordine di preferenza (dalla meno alla più impattante sul gameplay):

1. **Chiudere applicazioni terze** durante demo (browser, IDE, Claude Code)
2. **Eliminare il Judge** e auto-valutare le Condizioni nel JSON output di VOX (risparmia ~2 GB e ~2s/turno, perde controllo indipendente)
3. **Scendere a `whisper-medium`** invece di `large-v3-turbo` (risparmia ~700 MB, qualità STT comunque buona per italiano pulito)
4. **Modello VOX più piccolo** (`qwen2.5:3b`): ultima risorsa, qualità della trattativa ne risente

## Sicurezza e privacy

- Tutto on-device: nessun dato lascia la macchina del giocatore
- Le sessioni opzionalmente loggate in `logs/sessions/` (JSON con timestamp, trascrizioni, risposte VOX) **solo** se `SAVE_SESSION_LOGS=true` in `.env`
- Nessuna autenticazione o gestione utenti: il gioco gira in locale per un singolo giocatore alla volta

## Estensioni future (out of scope per esame)

- WebSocket per streaming audio bidirezionale (sostituzione di Streamlit con FastAPI + frontend custom)
- Voice cloning di VOX da sample audio caratteristico (richiederebbe F5-TTS, più pesante)
- Modalità multi-giocatore con detection di chi parla
- Logging strutturato delle sessioni con visualizzazione analytics (per debriefing post-gioco)
