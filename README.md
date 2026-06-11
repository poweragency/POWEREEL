# POWEREEL

Pipeline **end-to-end di reel finanziari automatici**: dagli articoli RSS al video pubblicato su Instagram/Facebook, senza intervento umano. Dashboard web multi-utente con wizard a 6 step.

**Flusso:** RSS (CoinDesk, CoinTelegraph, Il Sole 24 Ore) → script italiano ~45s generato con Claude → video avatar parlante (HeyGen) → montaggio con sottotitoli stilizzati ed emoji (MoviePy + PIL) → pubblicazione Reels su Instagram/Facebook via Meta Graph API → video serviti a Meta da Cloudflare R2.

## Stack

Python 3.11 · FastAPI (`server.py`, porta 8080, reverse-proxy verso Streamlit interno) · Streamlit (`app.py`, wizard) · Anthropic API (`claude-sonnet-4-6`) · HeyGen v2/v3 (avatar + digital twin training) · MoviePy + Pillow + pilmoji + faster-whisper · APScheduler · boto3 (R2) · Meta Graph API.

## Avvio locale

```bash
python -m venv venv && venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env                              # riempire le chiavi (vedi sotto)

streamlit run app.py        # solo dashboard (porta 8501, dev)
python server.py            # stack completo come su Railway (porta 8080)
python -m src --now         # pipeline una-tantum da CLI
python -m src               # pipeline a cron (settings.yaml → schedule_cron)
```

## Architettura (`src/`)

| Modulo | Ruolo |
|---|---|
| `pipeline.py` | Orchestratore dei 5 stage (scraper→scriptwriter→avatar→editor→publisher) |
| `scraper.py` | Stage 1 — feed RSS → articoli JSON |
| `scriptwriter.py` | Stage 2 — Claude genera lo script (solo parlato, solo italiano; strip dei meta-leak) |
| `avatar.py` / `avatar_creator.py` | Stage 3 — video avatar HeyGen; "Crea Avatar" = digital twin v3 (upload consent video + training, QR per upload da telefono) |
| `editor.py` | Stage 4 — montaggio, sottotitoli stile "nicktrading_" (8 preset in `subtitle_presets.py`), emoji crypto, musica BG |
| `publisher.py` + `publishers/` | Stage 5 — IG Reels e Facebook Pages Reels (retry con tenacity, probe ffprobe) |
| `cdn.py` | Upload su **Cloudflare R2** e URL pubblico per Meta (vedi Gotcha) |
| `users.py` / `auth.py` / `oauth/facebook.py` | Multi-utente (store JSON in `DATA_DIR`), cookie HMAC persistente, OAuth Meta per-utente con auto-discovery di Pagine + account IG |
| `scheduler.py` / `storage.py` / `config_loader.py` | Cron, cleanup output (>7gg), config Pydantic da `config/settings.yaml` |

Output delle run in `output/<data>/` (articles.json, script.txt, avatar.mp4, final_reel.mp4).

## Env richieste (`.env.example`)

`ANTHROPIC_API_KEY` · `HEYGEN_API_KEY` · `META_ACCESS_TOKEN` · `META_APP_ID` · `META_APP_SECRET` · `INSTAGRAM_BUSINESS_ACCOUNT_ID` · `R2_ACCOUNT_ID` · `R2_ACCESS_KEY_ID` · `R2_SECRET_ACCESS_KEY` · `R2_BUCKET` · `R2_PUBLIC_URL` · (`PORT`, `PUBLIC_BASE_URL`, `DATA_DIR` opzionali)

## Deploy (Railway)

Nixpacks (`nixpacks.toml`: ffmpeg + fonts-noto-color-emoji) · `Procfile`/`railway.json`: `python server.py` · `runtime.txt`: Python 3.11 · volume su `/app/data` per lo user store. Verifica R2 con `python _r2_preflight.py`.

## Gotcha noti

1. **Meta errore 2207076 / Content-Length**: l'edge di Railway (Fastly) toglie il `Content-Length` dalle risposte HEAD e il CDN di Meta rifiuta il `video_url`. Soluzione implementata in `src/cdn.py` (docstring completo): upload su R2 con bucket pubblico, **niente presigned URL** (SigV4 lega il metodo: firmata per GET → 403 sul HEAD), chiavi a 128 bit di entropia + lifecycle 24h.
2. **Modello Anthropic**: usare `claude-sonnet-4-6` (il vecchio `sonnet-4-20250514` dava 404 — fix nel commit `40dc230`).
3. **Sottotitoli**: allineati allo **script generato**, non alla trascrizione Whisper (commit `211345c`).
4. **HeyGen**: polling 15s × 40 tentativi (10 min max); se il training del twin è lento usare un avatar di libreria.
5. **File di test nella root**: i 5 `.mp4` e lo screenshot in root sono artefatti di sviluppo, non parte del deploy — candidati a cleanup/`.gitignore`.

## Stato

Sviluppo principale fino a maggio 2026 (+ pagine legali giugno). Repo: `poweragency/POWEREEL`.
