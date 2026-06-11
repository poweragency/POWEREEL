# CLAUDE.md — POWEREEL

Guida per agenti AI su questo repo. Lingua: italiano per UI/contenuti/commit, inglese per identificatori.

## Cos'è

Pipeline automatica di **reel finanziari**: RSS → script con Claude → avatar HeyGen → montaggio sottotitolato → publish IG/FB. Dashboard Streamlit multi-utente dietro FastAPI. Dettagli completi nel [README](README.md) — leggilo prima.

## Comandi

```bash
pip install -r requirements.txt
streamlit run app.py        # dashboard dev (8501)
python server.py            # stack completo (8080)
python -m src --now         # pipeline one-shot
python _r2_preflight.py     # verifica configurazione R2
```

Non esistono test automatici né linter configurati: la verifica è il dry-run della pipeline (`config/settings.yaml → dry_run: true`).

## Regole e gotcha (NON regredire)

- **`src/cdn.py` è intoccabile senza leggere il suo docstring**: serve i video a Meta da R2 perché Railway/Fastly rompe il HEAD (errore Meta 2207076). Niente presigned URL (SigV4 method-binding). Bucket pubblico + entropy key + lifecycle 24h.
- **Modello Anthropic**: `claude-sonnet-4-6` o successivo, configurato in `config/settings.yaml`. Mai hardcodare modelli nei moduli.
- **Sottotitoli allineati allo script generato**, NON alla trascrizione Whisper.
- **Script solo italiano, solo parlato**: il system prompt vieta meta-testo; `scriptwriter.py` fa anche strip via regex — non rimuoverla.
- **Lo user store è un JSON per-utente** (`DATA_DIR`, volume Railway `/app/data`): contiene hash password, API key e token OAuth Meta. Mai loggarne il contenuto, mai committarlo.
- I file `.mp4` e lo screenshot nella root sono artefatti di test: non basarti su di loro, non aggiungerne altri (usare `output/`).

## Struttura

Vedi README → "Architettura". Config in `config/settings.yaml` (Pydantic in `config_loader.py`). Asset richiesti: `assets/fonts/BebasNeue-Regular.ttf`, `assets/music/default_bg.mp3`, preview preset generate da `scripts/generate_preset_previews.py`.

## Deploy

Railway (Nixpacks: ffmpeg + fonts emoji; avvio `python server.py`). Env nel README. Le pagine legali statiche sono in `static/`.
