"""Stage 5: Publish video to Instagram Reels via Meta Graph API."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config_loader import PublisherConfig
from .scraper import Article

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _probe_video(video_path: Path) -> str:
    """Run ffprobe and return a one-line summary of video/audio specs.

    Used for debugging Meta's ProcessingFailedError — when an upload fails
    we have an exact record of what we sent.
    """
    if not shutil.which("ffprobe"):
        return "ffprobe-not-available"
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels,pix_fmt,profile:format=duration,bit_rate,format_name",
                "-of", "default=noprint_wrappers=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"ffprobe-error: {result.stderr[:200]}"
        # Compress newlines into a single readable line
        return " | ".join(
            line.strip() for line in result.stdout.splitlines() if line.strip()
        )[:600]
    except Exception as e:
        return f"ffprobe-exception: {e}"


def _ensure_reels_compat(video_path: Path) -> Path:
    """Re-encode the video to a known-good Instagram Reels spec.

    moviepy's default output is a valid MP4 but Meta's Reels processor
    rejects it with ``ProcessingFailedError`` (HTTP 500) for subtle reasons
    that vary per account: non-yuv420p pixel format, variable framerate,
    moov atom at the end, audio sample rate, etc.

    This function produces a sibling ``*_reels.mp4`` that's H.264 high
    profile / yuv420p / constant 30fps / AAC 48kHz / faststart — the
    spec Meta documents for Reels publishing.

    Returns the path of the re-encoded file, or the original if ffmpeg
    is unavailable (caller will then attempt upload as-is).
    """
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not in PATH — uploading source video as-is")
        return video_path

    out_path = video_path.with_name(video_path.stem + "_reels.mp4")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-c:v", "libx264",
        # Baseline profile: no B-frames, widest compatibility. Meta's Reels
        # processor rejected High-profile output with error 2207076 even with
        # spec-compliant bitrate. Baseline also matches what the source video
        # uses (HeyGen/moviepy → Constrained Baseline).
        "-profile:v", "baseline",
        "-level:v", "4.0",
        "-bf", "0",                                # explicitly no B-frames
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        # Target ~5 Mbps for 1080p Reels (Meta recommends 1-25 Mbps).
        "-b:v", "5M",
        "-maxrate", "7M",
        "-bufsize", "10M",
        "-r", "30",                                # constant 30 fps
        "-g", "60",                                # GOP every 2s
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dims
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",                                # stereo
        "-movflags", "+faststart",                 # moov atom at start
        "-brand", "mp42",                          # MP4 brand
        str(out_path),
    ]
    logger.info("Source video specs: %s", _probe_video(video_path))
    logger.info("Re-encoding to Reels spec: %s → %s", video_path.name, out_path.name)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg re-encode failed:\n%s", proc.stderr[-1500:])
        return video_path  # fall back to source — upload will likely fail too
    logger.info(
        "Re-encode done in %.1fs (out=%.2f MB)",
        time.time() - t0, out_path.stat().st_size / 1_048_576,
    )
    logger.info("Re-encoded video specs: %s", _probe_video(out_path))
    return out_path


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


def _build_public_video_url(video_path: Path) -> str | None:
    """Return a public URL Meta's CDN can fetch the video from.

    Priority:
      0. If IG_USE_RESUMABLE_UPLOAD=1, return None unconditionally so the
         caller takes the resumable-upload branch (Meta uploads from us
         instead of fetching). Avoids the Fastly HEAD Content-Length strip
         entirely without needing an external CDN.
      1. Cloudflare R2 — when R2_* env vars are set. Scales cleanly with
         zero egress; bypasses Fastly the same way.
      2. Railway `/_video/{key}/{filename}` — local/dev fallback only;
         currently broken in production behind Fastly.
    """
    if os.environ.get("IG_USE_RESUMABLE_UPLOAD") == "1":
        return None

    from src import cdn

    if cdn.is_configured():
        try:
            return cdn.upload_and_presign(video_path)
        except Exception as e:
            logger.error("R2 upload failed (%s) — falling back to Railway URL", e)

    public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not public_base:
        return None
    try:
        rel = video_path.resolve().relative_to((PROJECT_ROOT / "output").resolve())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    return f"{public_base}/_video/{parts[0]}/{parts[-1]}"


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
    """Create a Reel media container, preferring video_url over resumable.

    Two strategies:
      1. PUBLIC_BASE_URL set + file under output/ → use `video_url` so Meta
         fetches our public route. Bypasses rupload.facebook.com which often
         returns ProcessingFailedError 500 even for spec-compliant videos.
      2. No public URL available → resumable upload (legacy path).

    Returns the container ID. Caller polls status then publishes.
    """
    file_size = video_path.stat().st_size
    public_url = _build_public_video_url(video_path)

    if public_url:
        logger.info(
            "Uploading reel via video_url: %s (%.2f MB, ig=%s)",
            public_url, file_size / 1_048_576, ig_account_id,
        )
        init_resp = httpx.post(
            f"{GRAPH_API}/{ig_account_id}/media",
            params={
                "media_type": "REELS",
                "video_url": public_url,
                "caption": caption,
                "share_to_feed": "true",  # publish in main feed too
                "access_token": access_token,
            },
            timeout=60,
        )
        if init_resp.status_code >= 400:
            body = init_resp.text[:600] if init_resp.text else "<empty>"
            logger.error(
                "IG /media (video_url) failed: HTTP %s — body: %s",
                init_resp.status_code, body,
            )
        init_resp.raise_for_status()
        container_id = init_resp.json()["id"]
        logger.info("Container creato (video_url): %s", container_id)
        return container_id

    # ── Fallback: resumable upload (only used if no PUBLIC_BASE_URL) ──
    logger.warning(
        "PUBLIC_BASE_URL not set or path not under output/ — falling back to resumable upload"
    )

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

    logger.info("Container creato (resumable): %s", container_id)

    if upload_url:
        with open(video_path, "rb") as f:
            video_data = f.read()

        logger.info(
            "Uploading reel: %s (%.2f MB, ig=%s)",
            video_path.name, file_size / 1_048_576, ig_account_id,
        )

        upload_resp = httpx.post(
            upload_url,
            content=video_data,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            timeout=300,
        )
        if upload_resp.status_code >= 400:
            body_preview = upload_resp.text[:800] if upload_resp.text else "<empty>"
            logger.error(
                "IG resumable upload failed: HTTP %s\n  URL: %s\n  Body: %s",
                upload_resp.status_code, upload_url, body_preview,
            )
        upload_resp.raise_for_status()
        logger.info("Video uploadato via resumable upload")

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
                # Only fields Meta documents on the container endpoint.
                # The `status` string contains the human-readable error
                # reason when status_code=ERROR (e.g. "Error: Video duration ...").
                "fields": "status_code,status",
                "access_token": access_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status_code", "UNKNOWN")

        logger.info(
            "Container poll %d/%d: status_code=%s status=%r",
            attempt, max_attempts, status, data.get("status", ""),
        )

        if status == "FINISHED":
            return

        if status == "ERROR":
            err_status = data.get("status", "Errore sconosciuto")
            logger.error("Container ERROR — full status string: %s", err_status)
            raise RuntimeError(f"Instagram container error: {err_status}")

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
    """Full publishing flow: re-encode → upload → poll → publish. Returns media ID."""
    caption = _build_caption(articles, config)
    logger.info("Caption generata (%d caratteri)", len(caption))

    # Re-encode to known-good Reels spec to avoid Meta's
    # ProcessingFailedError (HTTP 500 on rupload.facebook.com).
    upload_path = _ensure_reels_compat(video_path)

    # Upload video
    container_id = _upload_video(
        upload_path, ig_account_id, access_token, caption
    )

    # Wait for processing
    _poll_container_status(container_id, access_token)

    # Publish
    media_id = _publish_container(container_id, ig_account_id, access_token)

    return media_id
