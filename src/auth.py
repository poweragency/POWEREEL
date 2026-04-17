"""Meta Graph API token management."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from dotenv import set_key

from .config_loader import PROJECT_ROOT

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


def check_and_refresh_token(
    access_token: str,
    app_id: str,
    app_secret: str,
) -> str:
    """Check if Meta token is near expiry and refresh if needed.

    Returns the (possibly refreshed) access token.
    """
    if not access_token:
        logger.warning("META_ACCESS_TOKEN non configurato")
        return access_token

    # Debug the current token
    try:
        resp = httpx.get(
            f"{GRAPH_API}/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as e:
        logger.warning("Impossibile verificare il token Meta: %s", e)
        return access_token

    is_valid = data.get("is_valid", False)
    expires_at = data.get("expires_at", 0)

    if not is_valid:
        logger.error(
            "Token Meta NON valido! Rigenera manualmente su developers.facebook.com"
        )
        return access_token

    # Check if expires within 7 days (604800 seconds)
    import time

    seconds_left = expires_at - int(time.time())
    days_left = seconds_left / 86400

    if expires_at == 0:
        # Token that never expires (page token from long-lived user token)
        logger.info("Token Meta: non ha scadenza (page token permanente)")
        return access_token

    logger.info("Token Meta: scade tra %.1f giorni", days_left)

    if days_left > 7:
        return access_token

    # Refresh the token
    logger.info("Token in scadenza, tentativo di refresh...")
    try:
        resp = httpx.get(
            f"{GRAPH_API}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": access_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        new_token = resp.json().get("access_token")

        if new_token and new_token != access_token:
            # Save to .env
            env_path = PROJECT_ROOT / "config" / ".env"
            if not env_path.exists():
                env_path = PROJECT_ROOT / ".env"

            if env_path.exists():
                set_key(str(env_path), "META_ACCESS_TOKEN", new_token)
                logger.info("Token Meta rinnovato e salvato in %s", env_path)
            else:
                logger.warning(
                    "Token rinnovato ma .env non trovato. Nuovo token: %s...%s",
                    new_token[:10],
                    new_token[-5:],
                )

            return new_token
        else:
            logger.warning("Refresh token non ha restituito un nuovo token")
            return access_token

    except Exception as e:
        logger.error("Errore nel refresh del token Meta: %s", e)
        logger.error(
            "Rigenera manualmente il token su developers.facebook.com "
            "prima che scada tra %.1f giorni",
            days_left,
        )
        return access_token
