"""Stage 3: Generate avatar video using HeyGen API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config_loader import HeyGenConfig

logger = logging.getLogger(__name__)

HEYGEN_BASE = "https://api.heygen.com"


def _headers(api_key: str) -> dict:
    return {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _create_video(script: str, config: HeyGenConfig, api_key: str) -> str:
    """Submit video generation request, return video_id."""
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": config.avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": config.voice_id,
                },
                "background": {
                    "type": config.background_type,
                    "value": config.background_value,
                },
            }
        ],
        "dimension": {
            "width": config.video_width,
            "height": config.video_height,
        },
    }

    response = httpx.post(
        f"{HEYGEN_BASE}/v2/video/generate",
        json=payload,
        headers=_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError(f"HeyGen errore: {data['error']}")

    video_id = data["data"]["video_id"]
    logger.info("Video HeyGen creato, video_id: %s", video_id)
    return video_id


def _poll_status(video_id: str, config: HeyGenConfig, api_key: str) -> str:
    """Poll HeyGen until video is ready, return download URL."""
    for attempt in range(1, config.poll_max_attempts + 1):
        response = httpx.get(
            f"{HEYGEN_BASE}/v1/video_status.get",
            params={"video_id": video_id},
            headers=_headers(api_key),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()["data"]
        status = data.get("status", "unknown")

        logger.info(
            "HeyGen poll %d/%d: status=%s",
            attempt,
            config.poll_max_attempts,
            status,
        )

        if status == "completed":
            video_url = data["video_url"]
            logger.info("Video HeyGen pronto: %s", video_url)
            return video_url

        if status == "failed":
            error = data.get("error", "Errore sconosciuto")
            raise RuntimeError(f"HeyGen video generation fallita: {error}")

        time.sleep(config.poll_interval_seconds)

    raise TimeoutError(
        f"HeyGen timeout: video non pronto dopo {config.poll_max_attempts} tentativi "
        f"({config.poll_max_attempts * config.poll_interval_seconds}s)"
    )


def _download_video(video_url: str, output_path: Path) -> None:
    """Download the generated video."""
    with httpx.stream("GET", video_url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Video scaricato: %s (%.1f MB)", output_path, size_mb)


def generate_avatar_video(
    script: str,
    config: HeyGenConfig,
    api_key: str,
    output_dir: Path,
) -> Path:
    """Full flow: create video → poll → download."""
    if not config.avatar_id or not config.voice_id:
        raise ValueError(
            "avatar_id e voice_id devono essere configurati in settings.yaml. "
            "Vai su https://app.heygen.com per creare il tuo Digital Twin."
        )

    video_id = _create_video(script, config, api_key)
    video_url = _poll_status(video_id, config, api_key)

    output_path = output_dir / "avatar_raw.mp4"
    _download_video(video_url, output_path)

    return output_path
