"""Upload reel videos to Cloudflare R2 for Meta IG/FB publishing.

Why this exists: Railway's edge (Fastly) strips `Content-Length` from HEAD
responses, which makes Meta's CDN reject our `video_url` with error 2207076.
R2 over its public-dev URL serves both HEAD and GET correctly with proper
Content-Length, and has zero egress fees. R2 is S3-compatible so we use
boto3 for the upload, then return the bucket's public URL.

We don't presign because R2 enforces strict SigV4 method-binding: a URL
signed for GET 403s on HEAD (Meta does HEAD first). Public bucket access
is safe here because object keys carry 128 bits of entropy and a 24h
lifecycle rule deletes them after Meta has fetched.

Required env vars (set on Railway):
  R2_ACCOUNT_ID         Cloudflare account ID
  R2_ACCESS_KEY_ID      R2 API token access key
  R2_SECRET_ACCESS_KEY  R2 API token secret
  R2_BUCKET             bucket name (e.g. "poweragency-reels")
  R2_PUBLIC_URL         bucket's public-dev URL, no trailing slash
                        (e.g. "https://pub-xxx.r2.dev")
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_URL",
)


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


def upload_and_get_url(file_path: Path, key_prefix: str = "reels") -> str:
    """Upload a video to R2 and return its public URL Meta can fetch.

    The key carries 128 bits of randomness so URLs are unguessable.
    Bucket lifecycle rule deletes `reels/` and `preflight/` objects after
    24h — set up once via setup_lifecycle().
    """
    bucket = os.environ["R2_BUCKET"]
    public_base = os.environ["R2_PUBLIC_URL"].rstrip("/")
    key = f"{key_prefix}/{secrets.token_hex(16)}/{file_path.name}"

    client = _client()
    size_mb = file_path.stat().st_size / 1_048_576
    logger.info(
        "R2 upload start: %s (%.2f MB) → s3://%s/%s",
        file_path.name, size_mb, bucket, key,
    )
    client.upload_file(
        str(file_path), bucket, key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    url = f"{public_base}/{key}"
    logger.info("R2 upload done; public URL: %s", url)
    return url


def setup_lifecycle() -> None:
    """Apply 24h auto-delete rule to reels/ and preflight/ object prefixes.

    Idempotent: re-running just overwrites the bucket's lifecycle config
    with the same rules.
    """
    bucket = os.environ["R2_BUCKET"]
    client = _client()
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-reels-1d",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "reels/"},
                    "Expiration": {"Days": 1},
                },
                {
                    "ID": "expire-preflight-1d",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "preflight/"},
                    "Expiration": {"Days": 1},
                },
            ]
        },
    )
    logger.info("R2 lifecycle rules applied (1-day expiration on reels/ and preflight/)")
