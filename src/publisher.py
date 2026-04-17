"""Stage 5: Publish video to Instagram Reels via Meta Graph API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config_loader import PublisherConfig
from .scraper import Article

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


def _build_caption(
    articles: list[Article],
    config: PublisherConfig,
) -> str:
    """Build Instagram caption from template and articles."""
    # Create summary bullets
    bullets = []
    for art in articles[:3]:  # Max 3 news items in caption
        bullets.append(f"• {art.title} ({art.source})")
    summary_bullets = "\n".join(bullets)

    caption = config.caption_template.format(
        headline_emoji="📊",
        summary_bullets=summary_bullets,
    )

    return caption.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _upload_video(
    video_path: Path,
    ig_account_id: str,
    access_token: str,
    caption: str,
) -> str:
    """Upload video and create media container. Returns container ID."""
    file_size = video_path.stat().st_size

    # Step 1: Initialize resumable upload
    init_resp = httpx.post(
        f"{GRAPH_API}/{ig_account_id}/media",
        params={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    init_data = init_resp.json()
    container_id = init_data["id"]
    upload_url = init_data.get("uri")

    logger.info("Container creato: %s", container_id)

    if upload_url:
        # Step 2: Upload video binary via resumable upload
        with open(video_path, "rb") as f:
            video_data = f.read()

        upload_resp = httpx.post(
            upload_url,
            content=video_data,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            timeout=300,  # Large file upload can take a while
        )
        upload_resp.raise_for_status()
        logger.info("Video uploadato via resumable upload")
    else:
        # Fallback: container was created without resumable upload
        # This happens if the API version doesn't support it
        logger.info("Container creato senza resumable upload (video_url richiesto)")

    return container_id


def _poll_container_status(
    container_id: str,
    access_token: str,
    max_attempts: int = 30,
    interval: int = 30,
) -> None:
    """Poll until the media container is ready for publishing."""
    for attempt in range(1, max_attempts + 1):
        resp = httpx.get(
            f"{GRAPH_API}/{container_id}",
            params={
                "fields": "status_code,status",
                "access_token": access_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status_code", "UNKNOWN")

        logger.info(
            "Container poll %d/%d: status=%s", attempt, max_attempts, status
        )

        if status == "FINISHED":
            return

        if status == "ERROR":
            error_msg = data.get("status", "Errore sconosciuto")
            raise RuntimeError(f"Instagram container error: {error_msg}")

        time.sleep(interval)

    raise TimeoutError(
        f"Instagram container non pronto dopo {max_attempts * interval}s"
    )


def _publish_container(
    container_id: str,
    ig_account_id: str,
    access_token: str,
) -> str:
    """Publish the container as a Reel. Returns media ID."""
    resp = httpx.post(
        f"{GRAPH_API}/{ig_account_id}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    media_id = resp.json()["id"]
    logger.info("Reel pubblicato! Media ID: %s", media_id)
    return media_id


def publish_to_instagram(
    video_path: Path,
    articles: list[Article],
    config: PublisherConfig,
    ig_account_id: str,
    access_token: str,
) -> str:
    """Full publishing flow: upload → poll → publish. Returns media ID."""
    caption = _build_caption(articles, config)
    logger.info("Caption generata (%d caratteri)", len(caption))

    # Upload video
    container_id = _upload_video(
        video_path, ig_account_id, access_token, caption
    )

    # Wait for processing
    _poll_container_status(container_id, access_token)

    # Publish
    media_id = _publish_container(container_id, ig_account_id, access_token)

    return media_id
