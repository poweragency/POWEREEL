"""Facebook / Instagram OAuth flow for multi-tenant SaaS.

The platform (POWEREEL) has ONE central Meta App. Customers click
"Connect Facebook" in the dashboard, get redirected to Meta OAuth,
and after authorizing they're redirected back to our /oauth/facebook/callback.

We exchange the code for a long-lived user token, then auto-discover
the user's Pages + linked Instagram Business accounts, and save everything
to the customer's profile in users.json.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"
META_LOGIN_DIALOG = "https://www.facebook.com/v21.0/dialog/oauth"

# Permissions requested from the customer's Facebook account.
# Only scopes already approved for this Meta App in App Review are listed.
# Instagram publishing works with instagram_basic + instagram_content_publish
# (the FB Page is just used to discover the linked IG Business account).
#
# To enable native Facebook Page Reel publishing, submit App Review for
# `pages_manage_posts` and re-add it here. `publish_video` was deprecated
# by Meta — Reels now go through `pages_manage_posts`.
FACEBOOK_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
]


def build_facebook_authorize_url(
    app_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Generate the Meta OAuth login URL for the customer to click."""
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": ",".join(FACEBOOK_SCOPES),
        "response_type": "code",
    }
    return f"{META_LOGIN_DIALOG}?{urlencode(params)}"


def exchange_code_for_token(
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
) -> str:
    """Exchange the authorization code for a short-lived user access token."""
    resp = httpx.get(
        f"{GRAPH_API}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token exchange failed: {data}")
    logger.info("Short-lived user token ottenuto (expires_in=%s)", data.get("expires_in"))
    return data["access_token"]


def fetch_long_lived_user_token(
    app_id: str,
    app_secret: str,
    short_lived_token: str,
) -> dict:
    """Exchange short-lived token for long-lived (~60 days) user token.

    Returns dict {access_token, expires_in, token_type}.
    """
    resp = httpx.get(
        f"{GRAPH_API}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Long-lived token exchange failed: {data}")
    logger.info("Long-lived user token ottenuto (expires_in=%s)", data.get("expires_in"))
    return data


def discover_pages_and_ig(user_token: str) -> list[dict]:
    """List all Facebook Pages the user manages, with linked IG Business accounts.

    Returns: [
        {
            "page_id": "...",
            "page_name": "...",
            "page_access_token": "...",  # never expires (page tokens from long-lived user tokens)
            "instagram_business_account": {"id": "...", "username": "..."} | None,
        },
        ...
    ]
    """
    resp = httpx.get(
        f"{GRAPH_API}/me/accounts",
        params={
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "access_token": user_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("data", [])

    result = []
    for p in pages:
        ig = p.get("instagram_business_account")
        result.append({
            "page_id": p["id"],
            "page_name": p["name"],
            "page_access_token": p.get("access_token", ""),
            "instagram_business_account": (
                {"id": ig["id"], "username": ig.get("username", "")} if ig else None
            ),
        })
    logger.info("Trovate %d pagine FB (di cui %d con IG collegato)",
                len(result), sum(1 for p in result if p["instagram_business_account"]))
    return result


def make_state_token() -> str:
    """Generate a CSRF-safe random state token."""
    return secrets.token_urlsafe(32)
