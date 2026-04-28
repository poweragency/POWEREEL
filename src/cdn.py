"""Upload reel videos to Cloudflare R2 for Meta IG/FB publishing.

Why this exists: Railway's edge (Fastly) strips `Content-Length` from HEAD
responses, which makes Meta's CDN reject our `video_url` with error 2207076.
Hosting the video on R2 — which has zero egress fees and proper HEAD
semantics — bypasses that. R2 is S3-compatible so we use boto3.

Required env vars (set on Railway):
  R2_ACCOUNT_ID         Cloudflare account ID (visible in R2 dashboard URL)
  R2_ACCESS_KEY_ID      R2 API token access key
  R2_SECRET_ACCESS_KEY  R2 API token secret
  R2_BUCKET             bucket name (e.g. "poweragency-reels")

Optional:
  R2_PRESIGN_TTL        presigned-URL TTL in seconds (default 3600)
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def is_configured() -> bool:
    """True iff every R2_* env var is set."""
    return all(os.environ.get(k) for k in _REQUIRED)


def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", region_name="auto"),
    )


def upload_and_presign(file_path: Path, key_prefix: str = "reels") -> str:
    """Upload a video to R2 and return a presigned GET URL Meta can fetch.

    The key is randomized so URLs are unguessable and old filenames don't
    leak. Configure a bucket lifecycle rule to delete `reels/` objects
    after 1 day to keep storage cost at ~$0.
    """
    bucket = os.environ["R2_BUCKET"]
    ttl = int(os.environ.get("R2_PRESIGN_TTL", "3600"))
    key = f"{key_prefix}/{secrets.token_hex(16)}/{file_path.name}"

    client = _client()
    size_mb = file_path.stat().st_size / 1_048_576
    logger.info("R2 upload start: %s (%.2f MB) → s3://%s/%s", file_path.name, size_mb, bucket, key)
    client.upload_file(
        str(file_path), bucket, key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl,
    )
    logger.info("R2 upload done; presigned URL TTL=%ds", ttl)
    return url
