"""Multi-tenant user management — email/password auth + per-user API keys."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERS_FILE = PROJECT_ROOT / "config" / "users.json"
USERS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _hash_password(password: str) -> str:
    """PBKDF2-SHA256 with random salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    )
    return f"{salt}:{pwd_hash.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, stored_hash = stored.split(":")
    except ValueError:
        return False
    test_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    )
    return secrets.compare_digest(test_hash.hex(), stored_hash)


def _safe_email(email: str) -> str:
    """Convert email to a filesystem-safe identifier."""
    return re.sub(r"[^a-z0-9]+", "_", email.lower()).strip("_")


def _load_db() -> dict:
    if not USERS_FILE.exists():
        return {"users": []}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": []}


def _save_db(db: dict) -> None:
    USERS_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public API ───────────────────────────────────────────────────────────────


def list_users() -> list[dict]:
    """Return all users (without password hashes)."""
    db = _load_db()
    return [
        {
            "email": u["email"],
            "is_admin": u.get("is_admin", False),
            "created_at": u.get("created_at", ""),
            "has_keys": bool(u.get("api_keys", {}).get("heygen")),
        }
        for u in db.get("users", [])
    ]


def create_user(email: str, password: str, is_admin: bool = False) -> tuple[bool, str]:
    """Create a new user. Returns (success, message)."""
    email = email.lower().strip()
    if not email or "@" not in email:
        return False, "Email non valida"
    if len(password) < 6:
        return False, "Password troppo corta (min 6 caratteri)"

    db = _load_db()
    if any(u["email"] == email for u in db.get("users", [])):
        return False, "Utente già esistente"

    db.setdefault("users", []).append({
        "email": email,
        "password_hash": _hash_password(password),
        "is_admin": is_admin,
        "created_at": datetime.now().isoformat(),
        "api_keys": {},
    })
    _save_db(db)
    return True, "Utente creato"


def delete_user(email: str) -> bool:
    db = _load_db()
    original = len(db.get("users", []))
    db["users"] = [u for u in db.get("users", []) if u["email"] != email.lower().strip()]
    _save_db(db)
    return len(db["users"]) < original


def authenticate(email: str, password: str) -> dict | None:
    """Verify credentials. Returns user dict (without password) if valid."""
    email = email.lower().strip()
    db = _load_db()
    for user in db.get("users", []):
        if user["email"] == email and _verify_password(password, user["password_hash"]):
            return {
                "email": user["email"],
                "is_admin": user.get("is_admin", False),
                "api_keys": user.get("api_keys", {}),
            }
    return None


def get_user(email: str) -> dict | None:
    """Get user info (no password) by email."""
    email = email.lower().strip()
    db = _load_db()
    for user in db.get("users", []):
        if user["email"] == email:
            return {
                "email": user["email"],
                "is_admin": user.get("is_admin", False),
                "api_keys": user.get("api_keys", {}),
            }
    return None


def update_user_keys(email: str, keys: dict) -> bool:
    """Update API keys for a user. Merges with existing keys."""
    email = email.lower().strip()
    db = _load_db()
    for user in db.get("users", []):
        if user["email"] == email:
            user.setdefault("api_keys", {}).update(keys)
            _save_db(db)
            return True
    return False


def change_password(email: str, new_password: str) -> bool:
    email = email.lower().strip()
    if len(new_password) < 6:
        return False
    db = _load_db()
    for user in db.get("users", []):
        if user["email"] == email:
            user["password_hash"] = _hash_password(new_password)
            _save_db(db)
            return True
    return False


def get_user_settings_path(email: str) -> Path:
    """Per-user settings YAML file path."""
    safe = _safe_email(email)
    p = PROJECT_ROOT / "config" / "users" / f"{safe}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_user_output_dir(email: str) -> Path:
    """Per-user output folder."""
    safe = _safe_email(email)
    p = PROJECT_ROOT / "output" / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_admin_exists(admin_email: str, admin_password: str) -> None:
    """Bootstrap: create admin user if no users exist yet."""
    db = _load_db()
    if not db.get("users"):
        create_user(admin_email, admin_password, is_admin=True)
