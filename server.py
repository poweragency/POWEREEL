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


# ── Public video serve (for IG Reels video_url upload method) ────────────────
# Meta's resumable upload endpoint (rupload.facebook.com) returns
# ProcessingFailedError 500 for some account/payload combos, even when the
# video is spec-compliant. The reliable fallback is the `video_url` method:
# we expose the file at a public URL and Meta's servers fetch it themselves.

import re as _re_video

@app.api_route("/_video/{key}/{filename}", methods=["GET", "HEAD"])
async def serve_temp_video(key: str, filename: str):
    """Serve an output video file (dev/local fallback only).

    Production publishing uploads to Cloudflare R2 instead — see src/cdn.py.
    Reason: Railway's Fastly edge strips `Content-Length` from HEAD
    responses (verified empirically), so Meta's CDN rejects this URL with
    error 2207076 regardless of how the origin sets the header.
    """
    if not _re_video.match(r'^[\w\-:.]+$', key):
        return JSONResponse({"error": "invalid key"}, status_code=400)
    if not _re_video.match(r'^[\w\-.]+\.(mp4|mov)$', filename):
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    if key == "test":
        path = PROJECT_ROOT / "static" / "test" / filename
    else:
        path = PROJECT_ROOT / "output" / key / filename
    if not path.exists() or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)

    from fastapi.responses import FileResponse
    return FileResponse(path, media_type="video/mp4")


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


# ── Diagnostic publish endpoint ───────────────────────────────────────────────
# Lets us POST to Meta /media bypassing the dashboard, so we can isolate
# whether the recurring 2207076 is caused by re-encoding, the URL host, or
# the App. Removed once we've root-caused.

@app.get("/_diag/test_publish")
async def diag_test_publish(
    token: str = "",
    reencode: int = 1,
    poll_seconds: int = 90,
):
    """Pick the latest output/<date>/final*.mp4, optionally re-encode, upload
    to R2, POST /media, poll status. Returns full diagnostic JSON.

    Query params:
      token         must equal env DIAG_TOKEN
      reencode      1 = use _ensure_reels_compat output (default), 0 = source as-is
      poll_seconds  upper bound for status polling (default 90)
    """
    expected = os.environ.get("DIAG_TOKEN", "")
    if not expected or token != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    # Find most-recent output/YYYY-MM-DD dir
    output_root = PROJECT_ROOT / "output"
    if not output_root.exists():
        return JSONResponse({"error": "no output/ dir"}, status_code=404)
    date_dirs = [d for d in output_root.iterdir()
                 if d.is_dir() and d.name[:4].isdigit()]
    if not date_dirs:
        return JSONResponse({"error": "no date subdirs in output/"}, status_code=404)
    latest_dir = max(date_dirs, key=lambda d: d.stat().st_mtime)

    final_src = latest_dir / "final.mp4"
    if not final_src.exists():
        return JSONResponse(
            {"error": f"no final.mp4 in {latest_dir.name}"},
            status_code=404,
        )

    # Pick the file to publish
    from src.publisher import _ensure_reels_compat, _probe_video
    if reencode:
        target = _ensure_reels_compat(final_src)
    else:
        target = final_src
    specs = _probe_video(target)

    # Upload to R2 under a diag/ prefix (won't collide with prod reels/)
    from src import cdn
    if not cdn.is_configured():
        return JSONResponse({"error": "R2 not configured"}, status_code=500)

    public_url = cdn.upload_and_get_url(target, key_prefix="diag")

    # Independent CDN check from inside Railway
    head_resp = httpx.head(public_url, timeout=30, follow_redirects=True)
    head_info = {
        "status": head_resp.status_code,
        "content_length": head_resp.headers.get("content-length"),
        "content_type": head_resp.headers.get("content-type"),
        "accept_ranges": head_resp.headers.get("accept-ranges"),
    }

    # Get IG creds the same way the dashboard does
    from src.config_loader import load_config
    from src.auth import check_and_refresh_token
    cfg = load_config(check_ffmpeg=False)
    page_tok = cfg.facebook_page_access_token or check_and_refresh_token(
        cfg.meta_access_token, cfg.meta_app_id, cfg.meta_app_secret,
    )
    ig_id = cfg.instagram_business_account_id

    # POST /media — minimal params, no share_to_feed (eliminate that variable)
    media_resp = httpx.post(
        f"https://graph.facebook.com/v21.0/{ig_id}/media",
        params={
            "media_type": "REELS",
            "video_url": public_url,
            "caption": "DIAG test — please ignore",
            "access_token": page_tok,
        },
        timeout=60,
    )
    media_body = media_resp.text[:1500] if media_resp.text else ""
    if media_resp.status_code != 200:
        return JSONResponse({
            "step": "media_create_failed",
            "media_status": media_resp.status_code,
            "media_body": media_body,
            "video_url": public_url,
            "head": head_info,
            "specs": specs,
            "reencode": bool(reencode),
            "file_size": target.stat().st_size,
            "ig_account_id": ig_id,
        })

    container_id = media_resp.json().get("id")
    if not container_id:
        return JSONResponse({
            "step": "no_container_id",
            "media_body": media_body,
        }, status_code=500)

    # Poll
    deadline = time.time() + poll_seconds
    last_status: dict = {}
    poll_count = 0
    while time.time() < deadline:
        poll_count += 1
        poll_resp = httpx.get(
            f"https://graph.facebook.com/v21.0/{container_id}",
            params={"fields": "status,status_code", "access_token": page_tok},
            timeout=15,
        )
        last_status = poll_resp.json()
        sc = last_status.get("status_code", "")
        logger.info(
            "DIAG poll %d: container=%s status_code=%s",
            poll_count, container_id, sc,
        )
        if sc in ("FINISHED", "ERROR", "EXPIRED"):
            break
        await asyncio.sleep(5)

    return JSONResponse({
        "ok": last_status.get("status_code") == "FINISHED",
        "reencode": bool(reencode),
        "video_url": public_url,
        "head": head_info,
        "specs": specs,
        "file_size": target.stat().st_size,
        "ig_account_id": ig_id,
        "container_id": container_id,
        "final_status": last_status,
        "polls": poll_count,
        # NOTE: we do NOT call /media_publish — the container stays unpublished.
        # That way the test doesn't post to the user's feed.
    })


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
