"""POWEREEL main server — FastAPI + Streamlit launcher with reverse proxy.

Architecture (single Railway service, single port):

  Public PORT (FastAPI)
    ├── /oauth/*           → handled directly by FastAPI (OAuth callbacks)
    ├── /healthz           → simple health check
    └── /* (everything)    → reverse-proxied to internal Streamlit (port 8501)
        - HTTP requests via httpx
        - WebSocket connections (Streamlit's _stcore/stream) tunneled

Streamlit runs as a subprocess on 127.0.0.1:8501.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response, JSONResponse
import uvicorn
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("powereel.server")

PROJECT_ROOT = Path(__file__).parent
STREAMLIT_HOST = "127.0.0.1"
STREAMLIT_PORT = 8501
PUBLIC_PORT = int(os.getenv("PORT", "8080"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", f"http://localhost:{PUBLIC_PORT}")


# ── State token store (in-memory, fine for single-instance Railway) ──────────
# Maps state_token -> {"email": "...", "platform": "facebook", "created_at": ts}
_OAUTH_STATES: dict[str, dict] = {}
_STATE_TTL = 600  # 10 min


def _cleanup_old_states():
    """Remove states older than TTL."""
    now = time.time()
    expired = [k for k, v in _OAUTH_STATES.items() if now - v["created_at"] > _STATE_TTL]
    for k in expired:
        _OAUTH_STATES.pop(k, None)


# ── Streamlit subprocess management ──────────────────────────────────────────

_streamlit_proc: subprocess.Popen | None = None


def start_streamlit():
    """Launch Streamlit on internal port."""
    global _streamlit_proc
    if _streamlit_proc and _streamlit_proc.poll() is None:
        return
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        f"--server.port={STREAMLIT_PORT}",
        f"--server.address={STREAMLIT_HOST}",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--server.maxUploadSize=500",
        "--server.maxMessageSize=500",
        "--server.enableWebsocketCompression=false",
        "--browser.gatherUsageStats=false",
    ]
    logger.info("Avvio Streamlit subprocess: %s", " ".join(cmd))
    _streamlit_proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


def wait_for_streamlit(timeout: int = 60):
    """Poll until Streamlit responds to health check."""
    start = time.time()
    url = f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}/_stcore/health"
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200:
                logger.info("Streamlit pronto (%.1fs)", time.time() - start)
                return
        except Exception:
            pass
        time.sleep(1)
    logger.warning("Streamlit non ha risposto in %ds — proseguo lo stesso", timeout)


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="POWEREEL Server")


@app.on_event("startup")
async def on_startup():
    start_streamlit()
    # Don't block — Streamlit needs ~5-10s to come up
    await asyncio.to_thread(wait_for_streamlit, 60)


@app.on_event("shutdown")
async def on_shutdown():
    if _streamlit_proc:
        logger.info("Spegnimento Streamlit...")
        _streamlit_proc.send_signal(signal.SIGTERM)
        try:
            _streamlit_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _streamlit_proc.kill()


@app.get("/healthz")
async def healthz():
    return {"ok": True, "streamlit_running": _streamlit_proc is not None and _streamlit_proc.poll() is None}


# ── Static landing preview ───────────────────────────────────────────────────
# Served directly by FastAPI (bypasses Streamlit) to test the new landing
# without disrupting the existing flow. Promote to "/" once approved.

_LANDING_PATH = PROJECT_ROOT / "static" / "landing.html"


@app.get("/landing")
async def landing_preview():
    if not _LANDING_PATH.exists():
        return JSONResponse({"error": "landing.html not found"}, status_code=404)
    return Response(
        content=_LANDING_PATH.read_text(encoding="utf-8"),
        media_type="text/html; charset=utf-8",
    )


# ── OAuth: Facebook ───────────────────────────────────────────────────────────

@app.get("/oauth/facebook/start")
async def fb_oauth_start(email: str):
    """Customer clicks 'Connect Facebook' → we generate Meta authorize URL."""
    from src.oauth.facebook import build_facebook_authorize_url, make_state_token

    app_id = os.getenv("META_APP_ID", "")
    if not app_id:
        return JSONResponse(
            {"error": "META_APP_ID not configured on platform"},
            status_code=500,
        )

    state = make_state_token()
    _cleanup_old_states()
    _OAUTH_STATES[state] = {
        "email": email,
        "platform": "facebook",
        "created_at": time.time(),
    }

    redirect_uri = f"{PUBLIC_BASE_URL}/oauth/facebook/callback"
    url = build_facebook_authorize_url(app_id, redirect_uri, state)
    logger.info("OAuth start per %s → redirect to Meta", email)
    return RedirectResponse(url=url)


@app.get("/oauth/facebook/callback")
async def fb_oauth_callback(code: str = "", state: str = "", error: str = "",
                             error_description: str = ""):
    """Meta redirects here after customer authorizes (or denies)."""
    from src.oauth.facebook import (
        exchange_code_for_token, fetch_long_lived_user_token,
        discover_pages_and_ig,
    )
    from src import users as _users

    if error:
        return _oauth_done_html(
            ok=False,
            message=f"Autorizzazione negata: {error_description or error}",
        )

    state_data = _OAUTH_STATES.pop(state, None)
    if not state_data:
        return _oauth_done_html(ok=False, message="State non valido o scaduto. Riprova.")

    email = state_data["email"]
    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    redirect_uri = f"{PUBLIC_BASE_URL}/oauth/facebook/callback"

    try:
        short_tok = exchange_code_for_token(app_id, app_secret, redirect_uri, code)
        long_data = fetch_long_lived_user_token(app_id, app_secret, short_tok)
        user_token = long_data["access_token"]
        expires_in = long_data.get("expires_in", 5184000)

        pages = discover_pages_and_ig(user_token)
        if not pages:
            return _oauth_done_html(
                ok=False,
                message="Nessuna Pagina Facebook trovata sul tuo account. "
                        "Crea una Pagina FB prima di collegare.",
            )

        # Build the full list of pages (multi-account support).
        # Each entry has the FB Page + its linked IG (if any) — user picks which
        # to publish to in Step 6.
        meta_pages = []
        for p in pages:
            ig = p["instagram_business_account"]
            meta_pages.append({
                "page_id": p["page_id"],
                "page_name": p["page_name"],
                "page_access_token": p["page_access_token"],
                "instagram_business_account_id": ig["id"] if ig else "",
                "instagram_username": ig.get("username", "") if ig else "",
            })

        # Legacy single-account fields: keep populated for back-compat with the
        # existing pipeline (reads instagram_business_account_id directly).
        chosen = next((p for p in pages if p["instagram_business_account"]), pages[0])
        ig = chosen["instagram_business_account"]

        keys_to_save = {
            "meta_access_token": user_token,
            "meta_token_expires_at": int(time.time()) + int(expires_in),
            "meta_pages": meta_pages,
            "facebook_page_id": chosen["page_id"],
            "facebook_page_name": chosen["page_name"],
            "facebook_page_access_token": chosen["page_access_token"],
        }
        if ig:
            keys_to_save["instagram_business_account_id"] = ig["id"]
            keys_to_save["instagram_username"] = ig.get("username", "")

        _users.update_user_keys(email, keys_to_save)

        ig_count = sum(1 for p in meta_pages if p["instagram_business_account_id"])
        headline = (
            f"<b>{len(meta_pages)} pagin{'e' if len(meta_pages) != 1 else 'a'} Facebook</b> "
            f"connesse, di cui <b>{ig_count} con Instagram</b>."
        )
        return _oauth_done_html(ok=True, message=headline, pages=meta_pages)

    except Exception as e:
        logger.exception("OAuth callback error")
        return _oauth_done_html(ok=False, message=f"Errore: {e}")


def _oauth_done_html(ok: bool, message: str, pages: list | None = None) -> Response:
    """Return an HTML page that auto-closes (popup) or redirects.

    On success, optionally renders the list of newly-connected pages
    (with FB icon + IG handle chip) and a CTA to Step 6.
    """
    icon = "✅" if ok else "❌"
    color = "#22c55e" if ok else "#ef4444"

    pages_html = ""
    if ok and pages:
        rows = []
        for p in pages:
            ig_chip = ""
            if p.get("instagram_business_account_id"):
                ig_user = p.get("instagram_username", "")
                ig_chip = (
                    f'<span class="ig-chip">@{ig_user}</span>'
                    if ig_user else '<span class="ig-chip">IG</span>'
                )
            page_name = p.get("page_name", "?")
            rows.append(
                f'<div class="page-row">'
                f'  <div class="fb-dot">f</div>'
                f'  <div class="page-info">'
                f'    <div class="page-name">{page_name}</div>'
                f'    {ig_chip}'
                f'  </div>'
                f'</div>'
            )
        pages_html = (
            f'<div class="pages-list">'
            f'  <div class="pages-list-title">PAGINE COLLEGATE</div>'
            f'  {"".join(rows)}'
            f'</div>'
        )

    cta_html = (
        '<a href="/app" class="btn-primary">Vai allo Step 6 → scegli pagine</a>'
        '<button onclick="window.close()" class="btn-link">Chiudi questa scheda</button>'
        if ok else
        '<button onclick="window.close()" class="btn-primary">Chiudi e riprova</button>'
    )

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
      <meta charset="utf-8">
      <title>POWEREEL · Collegamento {'riuscito' if ok else 'fallito'}</title>
      <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Geist', system-ui, sans-serif; background: #0b0d1a;
                color: #fafafa; margin: 0; padding: 24px;
                display: flex; align-items: center; justify-content: center;
                min-height: 100vh; }}
        .box {{ background: linear-gradient(180deg, #1a1a2e 0%, #141422 100%);
                padding: 36px; border-radius: 20px;
                border: 1px solid rgba(255,255,255,.08);
                box-shadow: 0 24px 60px -16px rgba(0,0,0,.6),
                            0 0 0 3px {color}20;
                text-align: center; max-width: 520px; width: 100%; }}
        .icon {{ font-size: 3.5rem; margin-bottom: 12px; }}
        h1 {{ color: {color}; margin: 0 0 12px; font-size: 1.6rem;
              font-weight: 800; letter-spacing: -.02em; }}
        p {{ color: #d4d4d8; line-height: 1.55; margin: 0 0 18px; font-size: .98rem; }}
        .pages-list {{ background: rgba(255,255,255,.03);
                       border: 1px solid rgba(255,255,255,.08);
                       border-radius: 12px; padding: 14px 16px;
                       margin: 22px 0; text-align: left; }}
        .pages-list-title {{ font-size: 11px; letter-spacing: 2px;
                             color: #71717a; font-weight: 700; margin-bottom: 10px; }}
        .page-row {{ display: flex; align-items: center; gap: 12px;
                     padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,.05); }}
        .page-row:last-child {{ border-bottom: 0; }}
        .fb-dot {{ flex-shrink: 0; width: 32px; height: 32px;
                   background: #1877f2; color: white;
                   font-weight: 800; font-size: 1.1rem;
                   font-family: Georgia, serif;
                   border-radius: 8px;
                   display: flex; align-items: center; justify-content: center; }}
        .page-info {{ flex: 1; display: flex; align-items: center;
                      justify-content: space-between; gap: 12px; }}
        .page-name {{ color: #fafafa; font-weight: 600; font-size: .95rem; }}
        .ig-chip {{ background: linear-gradient(135deg, #fa7e1e, #d62976, #4f5bd5);
                    color: white; font-size: .72rem; font-weight: 700;
                    padding: 3px 9px; border-radius: 999px;
                    letter-spacing: .03em; }}
        .btn-primary {{ display: inline-block; background: linear-gradient(135deg,#ff2357,#e40014);
                        color: white; border: 0; padding: 12px 24px;
                        border-radius: 10px; cursor: pointer; font-size: .98rem;
                        font-weight: 700; text-decoration: none;
                        margin-top: 16px;
                        box-shadow: 0 12px 28px -8px rgba(255,35,87,.55);
                        transition: transform .15s ease, box-shadow .25s ease; }}
        .btn-primary:hover {{ transform: translateY(-2px);
                              box-shadow: 0 18px 36px -8px rgba(255,35,87,.7); }}
        .btn-link {{ display: block; background: transparent;
                     color: #71717a; border: 0; padding: 10px;
                     cursor: pointer; font-size: .88rem;
                     margin: 6px auto 0; font-family: inherit; }}
        .btn-link:hover {{ color: #d4d4d8; }}
      </style>
    </head>
    <body>
      <div class="box">
        <div class="icon">{icon}</div>
        <h1>{"Account collegato!" if ok else "Errore di collegamento"}</h1>
        <p>{message}</p>
        {pages_html}
        {cta_html}
      </div>
    </body>
    </html>
    """
    return Response(content=html, media_type="text/html")


# ── HTTP reverse proxy to Streamlit ───────────────────────────────────────────

_proxy_client = httpx.AsyncClient(
    base_url=f"http://{STREAMLIT_HOST}:{STREAMLIT_PORT}",
    timeout=httpx.Timeout(60.0, connect=5.0),
    follow_redirects=False,
)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
)
async def proxy_to_streamlit(path: str, request: Request):
    """Forward all non-OAuth requests to internal Streamlit."""
    url = "/" + path
    qs = request.url.query
    if qs:
        url += "?" + qs

    # Filter hop-by-hop headers.
    # content-encoding/content-length are stripped because httpx auto-decompresses
    # resp.content; passing the original gzip headers would make the browser try to
    # gunzip already-decompressed bytes (→ blank page).
    hop_by_hop = {"connection", "keep-alive", "proxy-authenticate",
                  "proxy-authorization", "te", "trailers", "transfer-encoding",
                  "upgrade", "host", "content-encoding", "content-length"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop}

    body = await request.body()

    try:
        resp = await _proxy_client.request(
            method=request.method, url=url, headers=headers, content=body,
        )
    except httpx.ConnectError:
        return JSONResponse(
            {"error": "Streamlit not reachable, please retry in a few seconds"},
            status_code=503,
        )

    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in hop_by_hop}
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=resp.headers.get("content-type"),
    )


# ── WebSocket proxy for Streamlit's _stcore/stream ────────────────────────────

@app.websocket("/{path:path}")
async def proxy_websocket(websocket: WebSocket, path: str):
    """Proxy WebSocket connections to Streamlit (for live updates)."""
    target_url = f"ws://{STREAMLIT_HOST}:{STREAMLIT_PORT}/{path}"
    qs = websocket.url.query
    if qs:
        target_url += "?" + qs

    # Forward subprotocols to upstream so Streamlit can negotiate.
    # Without this, the browser sends Sec-WebSocket-Protocol but our accept()
    # echoes nothing back → browser drops the connection immediately.
    requested_subprotocols = websocket.scope.get("subprotocols") or []

    try:
        async with websockets.connect(
            target_url,
            subprotocols=requested_subprotocols or None,
        ) as upstream:
            # Echo the upstream-selected subprotocol back to the client.
            await websocket.accept(subprotocol=upstream.subprotocol)

            async def client_to_upstream():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.receive":
                            data = msg.get("text") or msg.get("bytes")
                            if data is not None:
                                await upstream.send(data)
                        elif msg["type"] == "websocket.disconnect":
                            break
                except Exception:
                    pass

            async def upstream_to_client():
                try:
                    async for data in upstream:
                        if isinstance(data, bytes):
                            await websocket.send_bytes(data)
                        else:
                            await websocket.send_text(data)
                except Exception:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS proxy error for %s: %s", target_url, e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("POWEREEL server starting on port %d (PUBLIC_BASE_URL=%s)",
                PUBLIC_PORT, PUBLIC_BASE_URL)
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PUBLIC_PORT,
        log_level="info",
        ws="websockets",
    )
