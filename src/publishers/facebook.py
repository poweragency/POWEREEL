"""Facebook Pages Reels publisher — Meta Graph API /video_reels endpoint.

Reuses the Meta App + Page tokens already configured for Instagram. Adds a
Facebook Page upload using the dedicated Reels endpoint so videos are
classified as Reels (not regular page videos).

Required Meta App permissions (incremental review on top of IG ones):
- pages_manage_posts
- publish_video

Token used: a Page access token (NOT user token) for the FB Page where the
Reel should be published.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config_loader import PublisherConfig
from src.scraper import Article

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"
RUPLOAD = "https://rupload.facebook.com/video-upload/v21.0"


def _build_facebook_caption(articles: list[Article], config: PublisherConfig) -> str:
    """Caption Facebook style — leggermente più narrativa di IG.

    For now reuses the IG template; Phase 3 (per-platform captions) will
    generate a longer Facebook-specific version with Claude.
    """
    bullets = []
    for art in articles[:3]:
        bullets.append(f"• {art.title} ({art.source})")
    summary_bullets = "\n".join(bullets)
    return config.caption_template.format(
        headline_emoji="📊",
        summary_bullets=summary_bullets,
    ).strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _start_upload(page_id: str, page_token: str) -> tuple[str, str]:
    """Phase 1: start a Reels upload session, returns (video_id, upload_url)."""
    resp = httpx.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={"upload_phase": "start", "access_token": page_token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "video_id" not in data:
        raise RuntimeError(f"Facebook upload start failed: {data}")
    upload_url = data.get("upload_url") or f"{RUPLOAD}/{data['video_id']}"
    logger.info("FB Reels upload started, video_id=%s", data["video_id"])
    return data["video_id"], upload_url


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _upload_binary(upload_url: str, video_path: Path, page_token: str) -> None:
    """Phase 2: upload the actual video bytes."""
    file_size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    resp = httpx.post(
        upload_url,
        content=video_bytes,
        headers={
            "Authorization": f"OAuth {page_token}",
            "offset": "0",
            "file_size": str(file_size),
        },
        timeout=300,
    )
    resp.raise_for_status()
    logger.info("FB Reels binary uploaded (%.1f MB)", file_size / 1024 / 1024)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _finish_upload(
    page_id: str,
    page_token: str,
    video_id: str,
    description: str,
) -> str:
    """Phase 3: finish upload and publish the Reel. Returns the post id."""
    resp = httpx.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
            "access_token": page_token,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Facebook publish failed: {data}")
    logger.info("FB Reel pubblicato! video_id=%s", video_id)
    return video_id


def _get_page_token(user_token: str, page_id: str) -> str:
    """Exchange user access token + page id for a Page access token."""
    resp = httpx.get(
        f"{GRAPH_API}/{page_id}",
        params={"fields": "access_token", "access_token": user_token},
        timeout=15,
    )
    resp.raise_for_status()
    page_token = resp.json().get("access_token", "")
    if not page_token:
        raise RuntimeError(
            "Impossibile ottenere il Page access token. "
            "Verifica che il token utente abbia i permessi sulla Pagina FB."
        )
    return page_token


def publish_to_facebook(
    video_path: Path,
    articles: list[Article],
    config: PublisherConfig,
    page_id: str,
    user_access_token: str,
) -> str:
    """Full FB Reels publish flow: start → upload → finish. Returns video_id."""
    if not page_id:
        raise ValueError("FACEBOOK_PAGE_ID non configurato")
    if not user_access_token:
        raise ValueError("META_ACCESS_TOKEN non configurato")

    caption = _build_facebook_caption(articles, config)
    logger.info("FB caption (%d caratteri)", len(caption))

    page_token = _get_page_token(user_access_token, page_id)

    video_id, upload_url = _start_upload(page_id, page_token)
    _upload_binary(upload_url, video_path, page_token)

    # Small delay before finish — Meta needs time to process the binary
    time.sleep(5)

    return _finish_upload(page_id, page_token, video_id, caption)
