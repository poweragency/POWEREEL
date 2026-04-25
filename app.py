"""POWEREEL — Step-by-step Wizard Dashboard."""

import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import httpx
import streamlit as st
import yaml
from dotenv import load_dotenv

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="POWEREEL",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",  # collapsed by default for mobile
)

# ── Mobile-friendly CSS + disable browser auto-translation ────────────────
_MOBILE_CSS = """
<style>
html, body { translate: no !important; }

@media (max-width: 768px) {
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        max-width: 100% !important;
    }
    h1 { font-size: 1.5rem !important; line-height: 1.3 !important; }
    h2 { font-size: 1.25rem !important; }
    h3 { font-size: 1.1rem !important; }
    h4 { font-size: 1rem !important; }
    .stButton > button {
        min-height: 48px !important;
        font-size: 1rem !important;
        padding: 0.6rem 1rem !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        margin-bottom: 0.5rem !important;
    }
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox > div > div,
    .stNumberInput input {
        font-size: 16px !important;
        min-height: 44px !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        min-height: 100px !important;
        padding: 1rem !important;
    }
    .stMetric label { font-size: 0.8rem !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    [data-testid="collapsedControl"] {
        background: #E8163C !important;
        border-radius: 50% !important;
        padding: 8px !important;
    }
}

@media (max-width: 480px) {
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    h1 { font-size: 1.3rem !important; }
    .stImage img { max-height: 200px !important; object-fit: contain !important; }
}
</style>
<script>
document.documentElement.setAttribute('translate', 'no');
document.documentElement.setAttribute('lang', 'it');
document.body.setAttribute('translate', 'no');
// Inject viewport meta into head if missing
(function() {
    if (!document.querySelector('meta[name="viewport"][content*="initial-scale"]')) {
        var m = document.createElement('meta');
        m.name = 'viewport';
        m.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
        document.head.appendChild(m);
    }
})();
</script>
"""

st.markdown(_MOBILE_CSS, unsafe_allow_html=True)


# ── Premium wizard CSS ───────────────────────────────────────────────────────
_WIZARD_CSS = """
<style>
/* Page typography accent */
.pwr-h1 {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
    letter-spacing: -.025em !important;
    background: linear-gradient(135deg, #fafafa 0%, #ff667f 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 6px !important;
    line-height: 1.1 !important;
}
.pwr-caption {
    color: #a1a1aa;
    font-size: .98rem;
    margin-bottom: 28px;
}

/* Section labels (PASSO, AVATAR, LOOK, etc.) */
.pwr-section-label {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #ff667f;
    background: rgba(255, 35, 87, .10);
    border: 1px solid rgba(255, 35, 87, .25);
    padding: 5px 11px;
    border-radius: 999px;
    margin-bottom: 14px;
}

/* Avatar / Look card (used for both group preview and per-look) */
.pwr-card {
    position: relative;
    background: linear-gradient(180deg, #1a1a2e 0%, #141422 100%);
    border: 1px solid rgba(255, 255, 255, .08);
    border-radius: 16px;
    padding: 8px 8px 0;
    transition: transform .28s cubic-bezier(.2,.7,.3,1),
                border-color .25s ease,
                box-shadow .28s ease;
    overflow: hidden;
    cursor: pointer;
}
.pwr-card:hover {
    transform: translateY(-4px);
    border-color: rgba(255, 35, 87, .35);
    box-shadow: 0 18px 40px -14px rgba(255, 35, 87, .35);
}
.pwr-card.selected {
    border: 2px solid #ff2357;
    box-shadow:
        0 0 0 3px rgba(255, 35, 87, .12),
        0 18px 50px -12px rgba(255, 35, 87, .55);
    background: linear-gradient(180deg, rgba(255,35,87,.07) 0%, #141422 65%);
}

/* Image wrapper — 4/5 aspect, faces at upper-third */
.pwr-card-img {
    position: relative;
    width: 100%;
    aspect-ratio: 4 / 5;
    border-radius: 11px;
    overflow: hidden;
    background: linear-gradient(135deg, #0f0f1e, #1a1a2e);
}
.pwr-card-img img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: 50% 18%;  /* keeps faces visible, no chin chop */
    display: block;
    transition: transform .5s ease;
}
.pwr-card:hover .pwr-card-img img { transform: scale(1.05); }

/* Gradient overlay at bottom of image, for premium feel */
.pwr-card-img::after {
    content: "";
    position: absolute;
    inset: auto 0 0 0;
    height: 35%;
    background: linear-gradient(0deg, rgba(10,10,18,.85) 0%, transparent 100%);
    pointer-events: none;
}

/* Wide variant — for video-frame previews (subtitle styles, HeyGen built-in) */
.pwr-card-img.wide {
    aspect-ratio: 16 / 9;
    background: #000;  /* match the dark video frame edge */
}
.pwr-card-img.wide img {
    object-fit: contain;       /* preserve full preview, don't crop subtitles */
    object-position: center;
}
.pwr-card-img.wide::after {
    display: none;             /* no bottom-fade overlay on previews */
}
.pwr-card:hover .pwr-card-img.wide img { transform: none; }  /* no zoom on previews */

/* "Active" pill in top-right of image */
.pwr-active-pill {
    position: absolute;
    top: 12px; right: 12px;
    padding: 5px 11px;
    border-radius: 999px;
    background: linear-gradient(135deg, #22c55e 0%, #15803d 100%);
    color: white;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .06em;
    box-shadow: 0 4px 14px rgba(34,197,94,.45);
    z-index: 2;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

/* Card name */
.pwr-card-name {
    padding: 12px 8px 4px;
    font-size: .92rem;
    font-weight: 600;
    text-align: center;
    color: #e4e4e7;
    line-height: 1.3;
}
.pwr-card-meta {
    padding: 0 8px 12px;
    font-size: .78rem;
    color: #71717a;
    text-align: center;
    letter-spacing: .03em;
    line-height: 1.45;
    min-height: 2.6em;       /* keep ~2 lines worth of vertical space so cards align */
    display: -webkit-box;
    -webkit-line-clamp: 3;   /* max 3 lines, ellipsis after */
    -webkit-box-orient: vertical;
    overflow: hidden;
}

/* Streamlit button polish */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: transform .15s ease, box-shadow .25s ease, background .2s ease, opacity .2s ease !important;
    border: 1px solid rgba(255,255,255,.12) !important;
    background: rgba(255,255,255,.04) !important;
}
.stButton > button:hover:not(:disabled) {
    transform: translateY(-1px) !important;
    background: rgba(255,255,255,.08) !important;
    border-color: rgba(255,255,255,.22) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #ff2357 0%, #e40014 100%) !important;
    border: 0 !important;
    color: white !important;
    box-shadow: 0 8px 22px -8px rgba(255, 35, 87, .55) !important;
}
.stButton > button[kind="primary"]:hover:not(:disabled) {
    box-shadow: 0 14px 32px -8px rgba(255, 35, 87, .7) !important;
}
.stButton > button:disabled {
    opacity: .55 !important;
    cursor: not-allowed !important;
}

/* Premium "Selected" button look (the green Attivo state below cards) */
.stButton > button[disabled]:has-text("Attivo"),
button[data-testid][kind="secondary"][disabled] {
    background: rgba(34,197,94,.12) !important;
    border-color: rgba(34,197,94,.4) !important;
    color: #4ade80 !important;
    opacity: 1 !important;
}

/* Tighten radio (avatar group) styling — though we now use cards */
[data-testid="stRadio"] > div {
    gap: 8px !important;
}
[data-testid="stRadio"] label {
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.08);
    padding: 8px 14px !important;
    border-radius: 999px !important;
    transition: all .2s ease;
    cursor: pointer;
}
[data-testid="stRadio"] label:has(input:checked) {
    background: linear-gradient(135deg, rgba(255,35,87,.18), rgba(228,0,20,.10));
    border-color: rgba(255,35,87,.5);
    color: white;
    box-shadow: 0 4px 14px -4px rgba(255,35,87,.4);
}

/* Soft divider */
hr, [data-testid="stDivider"] {
    border: 0 !important;
    border-top: 1px solid rgba(255,255,255,.08) !important;
    margin: 28px 0 !important;
}

/* Subheader polish */
h2, h3, .stSubheader {
    font-weight: 700 !important;
    letter-spacing: -.015em !important;
}

/* Sidebar refinements */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f0f1e 0%, #08090f 100%) !important;
}

/* Metric cards (credits) */
[data-testid="stMetric"] {
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 12px;
    padding: 12px 14px;
}

/* ── Account cards (Step 6) ───────────────────────────────────── */
.pwr-account-card .pwr-acct-banner {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    border-radius: 11px;
    overflow: hidden;
    background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
    display: flex;
    align-items: center;
    justify-content: center;
}
.pwr-acct-icon-row {
    display: flex;
    gap: 14px;
    align-items: center;
    z-index: 1;
}
.pwr-acct-icon {
    width: 56px; height: 56px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 10px 28px -8px rgba(0,0,0,.6);
    transition: transform .25s ease, box-shadow .25s ease;
}
.pwr-acct-icon.fb {
    background: #1877f2;
    box-shadow: 0 10px 28px -8px rgba(24,119,242,.5);
}
.pwr-acct-icon.ig {
    background:
        radial-gradient(circle at 30% 110%, #fdcb52 0%, #fa7e1e 12%, #d62976 38%,
                        #962fbf 60%, #4f5bd5 100%);
    box-shadow: 0 10px 28px -8px rgba(214,41,118,.55);
}
.pwr-account-card:hover .pwr-acct-icon { transform: scale(1.06); }

.pwr-account-card.selected .pwr-acct-banner {
    background:
        radial-gradient(ellipse at 50% 0%, rgba(255,35,87,.18) 0%, transparent 70%),
        linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
}

.pwr-acct-ig-label {
    color: #ff667f;
    font-weight: 600;
    font-size: .85rem;
    letter-spacing: .02em;
}
.pwr-acct-ig-label.muted {
    color: #71717a;
    font-weight: 400;
    font-style: italic;
}
</style>
"""
st.markdown(_WIZARD_CSS, unsafe_allow_html=True)


PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
ENV_PATH = PROJECT_ROOT / "config" / ".env"

# Load env
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
elif (PROJECT_ROOT / ".env").exists():
    load_dotenv(PROJECT_ROOT / ".env")

# Streamlit Cloud secrets
try:
    if hasattr(st, "secrets"):
        for key in ["HEYGEN_API_KEY", "ANTHROPIC_API_KEY", "META_ACCESS_TOKEN",
                     "META_APP_ID", "META_APP_SECRET", "INSTAGRAM_BUSINESS_ACCOUNT_ID",
                     "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN",
                     "PUBLIC_BASE_URL",
                     "APP_PASSWORD", "ADMIN_EMAIL", "ADMIN_PASSWORD"]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except Exception:
    pass


# ── Multi-tenant: bootstrap admin user ──
from src import users as _users

_admin_email = os.getenv("ADMIN_EMAIL", "info@poweragency.it")
_admin_password = os.getenv("ADMIN_PASSWORD") or os.getenv("APP_PASSWORD", "powereel2026")
_users.ensure_admin_exists(_admin_email, _admin_password)

# One-time: if admin user has no API keys but env has them (legacy/Railway secrets),
# seed admin's profile with those keys, then strip them from env so they don't leak
# to other users.
_admin_user = _users.get_user(_admin_email)
if _admin_user and not _admin_user.get("api_keys", {}).get("heygen"):
    _seed_keys = {}
    # Only seed PER-USER keys, never platform-wide credentials (Meta App)
    for env_name, profile_key in [
        ("HEYGEN_API_KEY", "heygen"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("META_ACCESS_TOKEN", "meta_access_token"),
        ("INSTAGRAM_BUSINESS_ACCOUNT_ID", "instagram_business_account_id"),
        ("FACEBOOK_PAGE_ID", "facebook_page_id"),
    ]:
        v = os.getenv(env_name)
        if v:
            _seed_keys[profile_key] = v
    if _seed_keys:
        _users.update_user_keys(_admin_email, _seed_keys)

# CRITICAL: clear PER-USER env API keys so they're never used as fallback.
# Each user must provide their own keys via the dashboard. Platform-wide
# credentials (META_APP_ID, META_APP_SECRET) stay in env — they belong to
# POWEREEL itself, not to a single customer.
for _env in [
    "HEYGEN_API_KEY", "ANTHROPIC_API_KEY", "META_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN",
]:
    if _env in os.environ:
        del os.environ[_env]


# Per-user API keys (each customer provides their own).
# NOTE: META_APP_ID and META_APP_SECRET are NOT here — they are PLATFORM-WIDE
# (set once in Railway env by the admin) because one single Meta App serves
# all customers via OAuth.
_API_KEY_MAPPING = {
    "heygen": "HEYGEN_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "meta_access_token": "META_ACCESS_TOKEN",
    "instagram_business_account_id": "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "facebook_page_id": "FACEBOOK_PAGE_ID",
    "facebook_page_access_token": "FACEBOOK_PAGE_ACCESS_TOKEN",
}

# Platform-wide env vars (from Railway secrets, never cleared on logout).
_PLATFORM_ENV_VARS = {"META_APP_ID", "META_APP_SECRET", "PUBLIC_BASE_URL"}


def _apply_user_api_keys(user: dict) -> None:
    """Inject ONLY this user's API keys into env vars. Clears all others first."""
    # Clear per-user env vars (not platform-wide ones)
    for env_name in _API_KEY_MAPPING.values():
        if env_name in os.environ and env_name not in _PLATFORM_ENV_VARS:
            del os.environ[env_name]
    # Set only those the user has
    keys = user.get("api_keys", {}) or {}
    for k, env_name in _API_KEY_MAPPING.items():
        if keys.get(k):
            os.environ[env_name] = keys[k]


# ── Authentication + Landing Page ───────────────────────────────────────────

def show_landing_and_login() -> bool:
    """Show interactive landing page with embedded login. Returns True if authenticated."""
    app_password = os.getenv("APP_PASSWORD", "")
    if not app_password:
        return True
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    # ── HERO section ──
    st.markdown("""
    <style>
    .hero {
        text-align: center;
        padding: 60px 20px 40px;
        background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
        border-radius: 16px;
        margin-bottom: 30px;
    }
    .hero h1 {
        font-size: 3.5rem !important;
        background: linear-gradient(90deg, #E8163C, #ff6b35);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0 0 12px !important;
        font-weight: 800;
    }
    .hero p {
        font-size: 1.2rem;
        color: #aaa;
        max-width: 700px;
        margin: 0 auto;
    }
    .feat-card {
        background: #1a1a2e;
        padding: 24px;
        border-radius: 12px;
        height: 100%;
        border: 1px solid #2a2a3e;
    }
    .feat-card h3 {
        color: #E8163C;
        margin-top: 0;
    }
    .feat-card p {
        color: #ccc;
        font-size: 0.95rem;
    }
    @media (max-width: 768px) {
        .hero h1 { font-size: 2rem !important; }
        .hero p { font-size: 1rem; }
        .hero { padding: 30px 15px; }
    }
    </style>

    <div class="hero">
        <h1>⚡ POWEREEL</h1>
        <p>Genera Reel Instagram automatici con il tuo avatar AI. <br>
        Notizie, script, voce, sottotitoli e pubblicazione: tutto in 5 minuti.</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Features grid ──
    st.markdown("### Cosa fa POWEREEL")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        st.markdown("""
        <div class="feat-card">
        <h3>📰 Notizie automatiche</h3>
        <p>Scraping in tempo reale dai feed RSS che scegli (CoinDesk, Cointelegraph, Sole24Ore...).
        Nessun copia-incolla manuale.</p>
        </div>
        """, unsafe_allow_html=True)
    with fc2:
        st.markdown("""
        <div class="feat-card">
        <h3>🎭 Avatar realistico</h3>
        <p>Il tuo clone HeyGen parla la tua voce. Scegli avatar, look e ambientazione
        direttamente dal pannello con anteprime visive.</p>
        </div>
        """, unsafe_allow_html=True)
    with fc3:
        st.markdown("""
        <div class="feat-card">
        <h3>🎬 Sottotitoli karaoke</h3>
        <p>Sottotitoli stile virali (nicktrading_) sincronizzati parola per parola con la voce
        grazie a Whisper. 4 preset pronti + personalizzazione totale.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    fc4, fc5, fc6 = st.columns(3)
    with fc4:
        st.markdown("""
        <div class="feat-card">
        <h3>📱 Pubblicazione Multi-Social</h3>
        <p>Reel pubblicati su <strong>Instagram + Facebook</strong> con un click via Meta Graph API.
        Presto anche TikTok e YouTube Shorts.</p>
        </div>
        """, unsafe_allow_html=True)
    with fc5:
        st.markdown("""
        <div class="feat-card">
        <h3>💰 Centro Costi</h3>
        <p>Vedi in tempo reale quanto costa ogni reel, crediti rimanenti HeyGen
        e proiezione mensile dei costi.</p>
        </div>
        """, unsafe_allow_html=True)
    with fc6:
        st.markdown("""
        <div class="feat-card">
        <h3>✋ Modalità ibrida</h3>
        <p>Pieno automatico ($3/video) o semi-manuale ($0/video usando i crediti del piano HeyGen Business).
        Scegli tu.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # ── How it works ──
    st.markdown("### Come funziona")
    st.markdown("""
    1. **Configura una volta** — avatar, voce, fonti notizie, stile sottotitoli, account Instagram
    2. **Clicca "Genera"** — POWEREEL fa tutto: notizie → script Claude → avatar HeyGen → editing
    3. **Pubblica** — automatico su Instagram Reels, oppure scarichi e pubblichi tu

    **Tempo medio:** 5 minuti dal click al reel pubblicato.
    """)

    st.divider()

    # ── Login form (email + password, multi-tenant) ──
    st.markdown("### 🔒 Accedi al tuo account")
    cl1, cl2 = st.columns([2, 3])
    with cl1:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="tua@email.com")
            password = st.text_input("Password", type="password",
                                      placeholder="La tua password")
            submitted = st.form_submit_button("Accedi →", type="primary", use_container_width=True)
            if submitted:
                user = _users.authenticate(email, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user_email = user["email"]
                    st.session_state.is_admin = user["is_admin"]
                    _apply_user_api_keys(user)
                    st.rerun()
                else:
                    st.error("❌ Email o password errati")
    with cl2:
        st.info(
            "**POWEREEL è in beta privata.**\n\n"
            "Per ottenere un account scrivi a **info@poweragency.it**\n\n"
            "Riceverai email e password personali per accedere al tuo pannello dedicato."
        )

    return False


def logout():
    """Clear authentication and reset to landing."""
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.is_admin = False
    st.session_state.step = 1
    st.session_state.view = "wizard"
    # Clear PER-USER API key env vars (NOT platform-wide ones)
    for key in ["HEYGEN_API_KEY", "ANTHROPIC_API_KEY", "META_ACCESS_TOKEN",
                "INSTAGRAM_BUSINESS_ACCOUNT_ID",
                "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"]:
        if key in os.environ:
            del os.environ[key]
    st.rerun()


if not show_landing_and_login():
    st.stop()

# Re-apply current user's API keys on every script run
if st.session_state.get("user_email"):
    _curr_user = _users.get_user(st.session_state.user_email)
    if _curr_user:
        _apply_user_api_keys(_curr_user)


# ── Top bar with logout ──
def render_top_bar():
    """Render top-right logout button."""
    cols = st.columns([6, 1])
    with cols[1]:
        if st.button("🚪 Logout", key="top_logout", use_container_width=True):
            logout()


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_settings(s: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(s, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@st.cache_data(ttl=300)
def _get_heygen_data_cached(api_key: str) -> dict:
    """Get HeyGen avatars filtered to ONLY vertical/Reel format (9:16).
    Cached per api_key so different users don't share results."""
    from PIL import Image
    from io import BytesIO

    if not api_key:
        return {"groups": [], "looks": {}, "voices": []}
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/avatar_group.list",
            headers={"X-Api-Key": api_key}, timeout=15,
        )
        groups_raw = r.json().get("data", {}).get("avatar_group_list", [])

        looks = {}
        groups = []
        for g in groups_raw:
            r2 = httpx.get(
                f"https://api.heygen.com/v2/avatar_group/{g['id']}/avatars",
                headers={"X-Api-Key": api_key}, timeout=15,
            )
            if r2.status_code != 200:
                continue
            avatar_list = r2.json().get("data", {}).get("avatar_list", [])

            vertical_looks = []
            for a in avatar_list:
                lid = a.get("id") or a.get("avatar_id")
                if not lid:
                    continue
                img_url = a.get("image_url", "")
                if not img_url or not img_url.startswith("http"):
                    continue
                # Check if vertical (Reel format)
                try:
                    img_r = httpx.get(img_url, timeout=10)
                    img = Image.open(BytesIO(img_r.content))
                    w, h = img.size
                    if h <= w:
                        continue  # skip non-vertical
                except Exception:
                    continue

                vertical_looks.append({
                    "look_id": lid,
                    "name": a.get("name", "Default"),
                    "image_url": img_url,
                })

            if vertical_looks:
                looks[g["name"]] = vertical_looks
                groups.append(g)

        rv = httpx.get(
            "https://api.heygen.com/v2/voices",
            headers={"X-Api-Key": api_key}, timeout=15,
        )
        voices = [v for v in rv.json().get("data", {}).get("voices", []) if v.get("type") == "custom"]

        return {"groups": groups, "looks": looks, "voices": voices}
    except Exception as e:
        st.error(f"Errore HeyGen: {e}")
        return {"groups": [], "looks": {}, "voices": []}


def get_heygen_data() -> dict:
    """Wrapper that always passes the current user's HeyGen key (per-user cache)."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return {"groups": [], "looks": {}, "voices": []}
    return _get_heygen_data_cached(api_key)


@st.cache_data(ttl=120)
def _get_heygen_credits_cached(api_key: str) -> int:
    if not api_key:
        return -1
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/user/remaining_quota",
            headers={"X-Api-Key": api_key}, timeout=10,
        )
        return r.json().get("data", {}).get("remaining_quota", 0)
    except Exception:
        return -1


def get_heygen_credits() -> int:
    """Wrapper: per-user cache via api_key in cache key."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return -1
    return _get_heygen_credits_cached(api_key)


RUN_MARKER = PROJECT_ROOT / "logs" / "wizard_run.lock"
DONE_MARKER = PROJECT_ROOT / "logs" / "wizard_run.done"


def run_pipeline_background(dry_run: bool):
    """Launch pipeline as a fully detached subprocess."""
    log_path = PROJECT_ROOT / "logs" / "wizard_run.log"
    log_path.parent.mkdir(exist_ok=True)

    # Clean previous markers
    if DONE_MARKER.exists():
        DONE_MARKER.unlink()
    RUN_MARKER.write_text(str(time.time()))

    # Build the multi-account publish targets list and inject it into env
    # (subprocess inherits parent env). Pipeline reads META_PUBLISH_TARGETS
    # to know which Meta pages/IG accounts to publish to.
    import json as _json
    user_email = st.session_state.get("user_email", "")
    if user_email and not dry_run:
        u = _users.get_user(user_email) or {}
        u_keys = u.get("api_keys", {}) or {}
        meta_pages = u_keys.get("meta_pages", []) or []
        # Synth from legacy fields if needed
        if not meta_pages and (u_keys.get("facebook_page_id") or u_keys.get("instagram_business_account_id")):
            meta_pages = [{
                "page_id": u_keys.get("facebook_page_id", ""),
                "page_name": u_keys.get("facebook_page_name", "") or "Facebook Page",
                "page_access_token": u_keys.get("facebook_page_access_token", ""),
                "instagram_business_account_id": u_keys.get("instagram_business_account_id", ""),
                "instagram_username": u_keys.get("instagram_username", ""),
            }]
        # Filter to selected
        sel_ids = set(settings.get("publisher", {}).get("selected_pages", []))
        targets = [p for p in meta_pages if p["page_id"] in sel_ids]
        # If user hasn't picked anything but has accounts, default to ALL
        if not targets and meta_pages and not sel_ids:
            targets = meta_pages
        os.environ["META_PUBLISH_TARGETS"] = _json.dumps(targets)
    else:
        os.environ.pop("META_PUBLISH_TARGETS", None)

    # Wrapper script that runs pipeline + writes DONE marker at the end
    wrapper = (
        "from src.pipeline import run_pipeline\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"DONE = Path(r'{DONE_MARKER}')\n"
        f"LOCK = Path(r'{RUN_MARKER}')\n"
        "try:\n"
        f"    run_pipeline(dry_run={dry_run})\n"
        "    DONE.write_text('ok')\n"
        "except Exception as e:\n"
        "    DONE.write_text(f'error: {e}')\n"
        "    sys.exit(1)\n"
        "finally:\n"
        "    if LOCK.exists(): LOCK.unlink()\n"
    )

    def _run():
        with open(log_path, "w", encoding="utf-8") as logf:
            subprocess.run(
                [sys.executable, "-c", wrapper],
                stdout=logf, stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT), timeout=900,
            )

    threading.Thread(target=_run, daemon=True).start()


def is_generation_running() -> bool:
    """Check if a generation is currently running (file-based).
    Auto-cleanup if marker is stale (>30 min old)."""
    if not RUN_MARKER.exists():
        return False
    try:
        started = float(RUN_MARKER.read_text().strip())
        if time.time() - started > 1800:  # 30 min
            RUN_MARKER.unlink()
            DONE_MARKER.write_text("error: stuck process (auto-cleared after 30 min)")
            return False
    except Exception:
        return True
    return True


def get_generation_started_at() -> float:
    """Get start time of current generation, or 0."""
    if not RUN_MARKER.exists():
        return 0
    try:
        return float(RUN_MARKER.read_text().strip())
    except Exception:
        return time.time()


def get_generation_result() -> str | None:
    """Returns 'ok', 'error: ...', or None if not done yet."""
    if not DONE_MARKER.exists():
        return None
    return DONE_MARKER.read_text().strip()


# ── State ────────────────────────────────────────────────────────────────────

settings = load_settings()
data = get_heygen_data()

# ── Pricing constants (admin cost analysis) ─────────────────────────────────

# HeyGen: ~$0.066 per API credit (1500 credits = $99/mo Business pack)
HEYGEN_USD_PER_CREDIT = 0.066

# Claude Sonnet 4: $3/M input, $15/M output. Avg ~800 in + 250 out per script.
CLAUDE_USD_PER_SCRIPT = (800 * 3 / 1_000_000) + (250 * 15 / 1_000_000)  # ~$0.006


# Persist current step across refreshes via file
STEP_FILE = PROJECT_ROOT / "logs" / "current_step.txt"
STEP_FILE.parent.mkdir(exist_ok=True)


def _video_count_from_outputs() -> int:
    """Count generated videos in output/ folders."""
    out = PROJECT_ROOT / "output"
    if not out.exists():
        return 0
    count = 0
    for folder in out.iterdir():
        if folder.is_dir() and (folder / "final.mp4").exists():
            count += 1
    return count


def _read_step() -> int:
    if STEP_FILE.exists():
        try:
            return max(1, min(int(STEP_FILE.read_text().strip()), 7))
        except Exception:
            return 1
    return 1


def goto_step(n: int):
    n = max(1, min(n, 7))
    st.session_state.step = n
    STEP_FILE.write_text(str(n))


if "step" not in st.session_state:
    st.session_state.step = _read_step()

if "view" not in st.session_state:
    st.session_state.view = "wizard"  # "wizard" or "costs"

STEPS = [
    "1. Avatar e Look",
    "2. Voce",
    "3. Fonti Notizie",
    "4. Script e Tono",
    "5. Stile Sottotitoli",
    "6. Distribuzione Social",
    "7. Genera e Pubblica",
]

STEP_TITLES = {
    1: "Passo 1 — Avatar e Look",
    2: "Passo 2 — Voce",
    3: "Passo 3 — Fonti Notizie",
    4: "Passo 4 — Script e Tono",
    5: "Passo 5 — Stile Sottotitoli",
    6: "Passo 6 — Distribuzione Social",
    7: "Passo 7 — Genera e Pubblica",
}


# ── Top bar (logout) ──
render_top_bar()


# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("⚡ POWEREEL")
st.sidebar.caption(f"👤 {st.session_state.get('user_email', 'guest')}")

credits = get_heygen_credits()
if credits >= 0:
    st.sidebar.metric("Crediti HeyGen API", credits)
    remaining_value = credits * HEYGEN_USD_PER_CREDIT
    st.sidebar.caption(f"≈ ${remaining_value:.2f} rimasti")
elif credits == -1:
    st.sidebar.warning("⚠️ HeyGen API non configurata")

st.sidebar.divider()

# ── View switcher ──
if st.session_state.view == "wizard":
    st.sidebar.markdown("### Progresso")
    for i, name in enumerate(STEPS, 1):
        if i < st.session_state.step:
            st.sidebar.markdown(f"✅ {name}")
        elif i == st.session_state.step:
            st.sidebar.markdown(f"**🔵 {name}**")
        else:
            st.sidebar.markdown(f"⚪ {name}")

    st.sidebar.divider()
    if st.sidebar.button("🔄 Ricomincia da Step 1"):
        goto_step(1)
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### Account")

    if st.sidebar.button("🔑 Configura API Keys", use_container_width=True):
        st.session_state.view = "api_keys"
        st.rerun()

    if st.sidebar.button("📚 Guida Setup", use_container_width=True):
        st.session_state.view = "guide"
        st.rerun()

    if st.sidebar.button("💰 Centro Costi", use_container_width=True):
        st.session_state.view = "costs"
        st.rerun()

    if st.session_state.get("is_admin"):
        if st.sidebar.button("👥 Admin: Gestisci utenti", use_container_width=True):
            st.session_state.view = "admin"
            st.rerun()
else:
    if st.sidebar.button("← Torna al Wizard", use_container_width=True, type="primary"):
        st.session_state.view = "wizard"
        st.rerun()

st.sidebar.divider()
if st.sidebar.button("🚪 Logout", key="sidebar_logout", use_container_width=True):
    logout()


# ── Wizard navigation ───────────────────────────────────────────────────────

def nav_buttons(current_step: int, can_proceed: bool, next_label: str = "Avanti →"):
    col_back, col_space, col_next = st.columns([1, 3, 1])
    with col_back:
        if current_step > 1:
            if st.button("← Indietro", use_container_width=True):
                goto_step(current_step - 1)
                st.rerun()
    with col_next:
        if current_step < len(STEPS):
            if st.button(next_label, type="primary", use_container_width=True, disabled=not can_proceed):
                goto_step(current_step + 1)
                st.rerun()


# ── COST CENTER (admin) ─────────────────────────────────────────────────────

# ── API KEYS PAGE ────────────────────────────────────────────────────────────

if st.session_state.view == "api_keys":
    st.markdown('<h1 translate="no" lang="it">🔑 Configura le tue API Keys</h1>', unsafe_allow_html=True)
    st.caption("Inserisci le tue chiavi API per HeyGen, Anthropic (Claude) e Meta/Instagram. "
               "Queste chiavi sono salvate nel tuo profilo e non sono visibili ad altri utenti.")

    user = _users.get_user(st.session_state.user_email)
    current_keys = user.get("api_keys", {}) if user else {}

    with st.form("api_keys_form"):
        st.subheader("HeyGen")
        st.caption("La trovi su [app.heygen.com](https://app.heygen.com) → Settings → API")
        new_heygen = st.text_input(
            "HEYGEN_API_KEY",
            value=current_keys.get("heygen", ""),
            type="password",
            placeholder="sk_V2_hgu_...",
        )

        st.divider()
        st.subheader("Anthropic (Claude)")
        st.caption("La trovi su [console.anthropic.com](https://console.anthropic.com) → API Keys")
        new_anthropic = st.text_input(
            "ANTHROPIC_API_KEY",
            value=current_keys.get("anthropic", ""),
            type="password",
            placeholder="sk-ant-api03-...",
        )

        if st.form_submit_button("💾 Salva chiavi", type="primary"):
            _users.update_user_keys(st.session_state.user_email, {
                "heygen": new_heygen.strip(),
                "anthropic": new_anthropic.strip(),
            })
            st.success("✅ Chiavi salvate! Ricarica la pagina per applicarle ovunque.")

    st.divider()

    # ── Meta / Instagram / Facebook (OAuth — no manual token needed) ──
    st.subheader("Instagram + Facebook")
    st.caption(
        "Per pubblicare i reel su Instagram e Facebook **non serve nessuna chiave**. "
        "Basta cliccare 'Collega Facebook' e fare login con il tuo account social."
    )

    fb_page = current_keys.get("facebook_page_name") or current_keys.get("facebook_page_id")
    ig_user = current_keys.get("instagram_username")

    col_status, col_action = st.columns([3, 1])
    with col_status:
        if fb_page:
            st.success(f"✅ Pagina Facebook collegata: **{fb_page}**")
        if ig_user:
            st.success(f"✅ Instagram collegato: **@{ig_user}**")
        if not fb_page and not ig_user:
            st.info("Nessun account social ancora collegato.")
    with col_action:
        public_base = os.getenv("PUBLIC_BASE_URL", "")
        if public_base:
            oauth_url = f"{public_base}/oauth/facebook/start?email={st.session_state.user_email}"
            label = "🔄 Riconnetti" if (fb_page or ig_user) else "🔗 Collega Facebook"
            st.markdown(
                f'<a href="{oauth_url}" target="_blank" '
                f'style="display:block; padding:10px; background:#1877F2; color:white; '
                f'text-align:center; border-radius:8px; text-decoration:none; font-weight:bold;">'
                f'{label}</a>',
                unsafe_allow_html=True,
            )
            st.caption("Si apre una nuova scheda")
        else:
            st.warning("OAuth non configurato (manca PUBLIC_BASE_URL)")

    st.divider()
    st.info("💡 Non sai come ottenere queste chiavi? Vai su **Guida Setup** dalla sidebar.")

    st.stop()


# ── GUIDE PAGE ───────────────────────────────────────────────────────────────

if st.session_state.view == "guide":
    st.markdown('<h1 translate="no" lang="it">📚 Guida Setup POWEREEL</h1>', unsafe_allow_html=True)
    st.caption("Tutto quello che ti serve per configurare il tuo account in 15 minuti")

    st.markdown("""
    Per usare POWEREEL ti servono **3 cose principali**:
    1. Un account **HeyGen** (per generare i video con avatar AI)
    2. Un account **Anthropic / Claude** (per generare gli script)
    3. Un account **Instagram Business** + **Meta Developer App** (per pubblicare automaticamente — opzionale)

    Ti guido passo per passo.
    """)

    # ── HeyGen ──
    with st.expander("🎭 1. Setup HeyGen — Avatar AI", expanded=True):
        st.markdown("""
        **a) Registrati su HeyGen**

        - Vai su [https://www.heygen.com](https://www.heygen.com) e clicca **Sign Up**
        - Sottoscrivi il **piano Business** ($48-99/mese) — necessario per accesso API e Digital Twin

        **b) Crea il tuo Avatar (Digital Twin)**

        - Una volta dentro, vai su **Avatars** → **Create Avatar** → **Instant Avatar**
        - Carica un video di te stesso di **almeno 2 minuti** (girato in formato verticale 9:16)
        - Aspetta 1-2 ore per la creazione (HeyGen ti manda mail quando è pronto)

        **c) Clona la tua Voce**

        - Vai su **Voice** → **Create Voice** → **Instant Voice Clone**
        - Carica 30-60 secondi di audio della tua voce (chiara, no rumore)
        - Disponibile in pochi minuti

        **d) Ottieni la tua API Key**

        - Vai su **Settings** → **API** (in basso a sinistra)
        - Clicca **Create API Key** e copiala (formato `sk_V2_hgu_...`)
        - **IMPORTANTE:** acquista anche **API credits** separatamente (~$30 per 500 crediti) — sono diversi dai crediti del piano

        **e) Incolla la chiave in POWEREEL**

        - Vai su **🔑 Configura API Keys** nella sidebar e incolla `HEYGEN_API_KEY`
        """)

    # ── Anthropic ──
    with st.expander("🤖 2. Setup Anthropic / Claude — Script AI"):
        st.markdown("""
        **a) Registrati su Anthropic**

        - Vai su [https://console.anthropic.com](https://console.anthropic.com)
        - Crea un account con email
        - Aggiungi un metodo di pagamento (richiesto per usare l'API)

        **b) Aggiungi credito**

        - Vai su **Settings** → **Plans & Billing** → **Add Credits**
        - Aggiungi **$5-10** (basta per migliaia di script — costo per script: ~$0.006)

        **c) Crea API Key**

        - Vai su **Settings** → **API Keys** → **Create Key**
        - Dai un nome (es. "POWEREEL") e copia la chiave (formato `sk-ant-api03-...`)
        - **Salvala subito**: non sarà più visualizzabile dopo

        **d) Incolla la chiave in POWEREEL**

        - Vai su **🔑 Configura API Keys** → incolla `ANTHROPIC_API_KEY`
        """)

    # ── Instagram ──
    with st.expander("📱 3. Setup Instagram — Pubblicazione automatica (opzionale)"):
        st.markdown("""
        **Prerequisiti:**
        - Un account **Instagram Business** o **Creator** (non personale)
        - Una **Pagina Facebook** collegata all'account Instagram

        **a) Converti il tuo account a Business**

        - Su Instagram → **Impostazioni** → **Account** → **Passa ad account aziendale**

        **b) Collega l'account Instagram a una Pagina Facebook**

        - Su Instagram → **Impostazioni** → **Account collegati** → **Facebook** → seleziona la pagina

        **c) Crea una Meta Developer App**

        - Vai su [https://developers.facebook.com](https://developers.facebook.com)
        - **My Apps** → **Create App** → tipo **Business**
        - Nel menu sinistro: **Casi d'uso** → cerca **"Gestisci messaggi e contenuti su Instagram"** → **Personalizza**

        **d) Aggiungi i permessi**

        - Aggiungi questi permessi: `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`

        **e) Genera Token + Trova ID**

        - Vai su **Strumenti** → **Graph API Explorer**
        - Seleziona la tua app, aggiungi i permessi sopra
        - Clicca **Generate Access Token**
        - Copia: `META_ACCESS_TOKEN`
        - In **Settings → Basic** copia: `META_APP_ID` e `META_APP_SECRET`
        - Per `INSTAGRAM_BUSINESS_ACCOUNT_ID`: usa il Graph Explorer e fai una GET su `me/accounts?fields=instagram_business_account` — l'ID che trovi è quello che ti serve

        **f) Incolla tutto in POWEREEL**

        - Vai su **🔑 Configura API Keys** → incolla i 4 valori Meta/Instagram
        """)

    # ── Facebook ──
    with st.expander("👥 4. Setup Facebook Pages — Pubblica anche su Facebook (opzionale)"):
        st.markdown("""
        **Buona notizia:** se hai già configurato Instagram al punto 3, hai già la maggior
        parte di quello che ti serve. La stessa Meta App e lo stesso `META_ACCESS_TOKEN`
        sono validi anche per Facebook.

        **Cosa serve in più:**

        **a) Una Pagina Facebook attiva**

        - Devi essere admin della Pagina FB su cui vuoi pubblicare i Reels
        - Va bene la stessa Pagina FB collegata al tuo account Instagram Business

        **b) Permessi Meta App aggiuntivi**

        - Sulla tua Meta Developer App, in **Casi d'uso** aggiungi i permessi:
          - `pages_manage_posts`
          - `publish_video`
        - Sottoponi a **App Review** (di solito 3-7 giorni di approvazione, più veloce
          se la tua app è già approvata per Instagram)

        **c) Trova `FACEBOOK_PAGE_ID`**

        - Vai su **Strumenti → Graph API Explorer**
        - Fai una GET su `me/accounts` con il tuo token
        - Copia l'`id` della Pagina su cui vuoi pubblicare

        **d) Incolla in POWEREEL**

        - Vai su **🔑 Configura API Keys** → incolla `FACEBOOK_PAGE_ID`
        - Nel **Passo 6 — Distribuzione Social** del wizard troverai il toggle per
          attivare la pubblicazione su Facebook
        """)

    st.divider()
    st.success("Una volta inserite le chiavi, vai al **Wizard** e configura il tuo primo reel!")

    if st.button("🔑 Vai a Configura API Keys", type="primary"):
        st.session_state.view = "api_keys"
        st.rerun()

    st.stop()


# ── ADMIN PAGE ───────────────────────────────────────────────────────────────

if st.session_state.view == "admin":
    if not st.session_state.get("is_admin"):
        st.error("Accesso negato — solo admin")
        st.stop()

    st.markdown('<h1 translate="no" lang="it">👥 Admin — Gestione Utenti</h1>', unsafe_allow_html=True)

    st.subheader("Crea nuovo utente")
    with st.form("create_user_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            new_email = st.text_input("Email", placeholder="cliente@example.com")
        with c2:
            new_password = st.text_input("Password", placeholder="min 6 caratteri")
        with c3:
            is_admin_new = st.checkbox("Admin")
        if st.form_submit_button("➕ Crea utente", type="primary"):
            ok, msg = _users.create_user(new_email, new_password, is_admin=is_admin_new)
            if ok:
                st.success(f"✅ {msg}: {new_email}")
            else:
                st.error(f"❌ {msg}")

    st.divider()
    st.subheader("Utenti esistenti")
    users_list = _users.list_users()
    if not users_list:
        st.info("Nessun utente ancora")
    else:
        for u in users_list:
            c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
            with c1:
                badge = "👑 admin" if u["is_admin"] else "👤"
                keys_badge = "🔑" if u["has_keys"] else "⚪"
                st.write(f"{badge} {keys_badge} **{u['email']}**")
            with c2:
                st.caption(u["created_at"][:10])
            with c3:
                with st.popover("🔁 Reset password"):
                    new_pw = st.text_input(
                        "Nuova password", type="password", key=f"reset_{u['email']}"
                    )
                    if st.button("Conferma", key=f"reset_btn_{u['email']}"):
                        if _users.change_password(u["email"], new_pw):
                            st.success("Password aggiornata")
                        else:
                            st.error("Errore (min 6 caratteri)")
            with c4:
                if u["email"] != st.session_state.user_email:
                    if st.button("🗑️", key=f"del_{u['email']}"):
                        _users.delete_user(u["email"])
                        st.rerun()

    st.stop()


if st.session_state.view == "costs":
    st.markdown('<h1 translate="no" lang="it">💰 Centro Costi</h1>', unsafe_allow_html=True)
    st.caption("Analisi dettagliata dei costi per la generazione dei reel")

    target_duration = settings["scriptwriter"]["target_duration_seconds"]

    # ── Cost per video ──
    st.subheader("📹 Costo per video")

    heygen_credits_per_video = target_duration  # ~1 credit/sec
    heygen_cost_per_video = heygen_credits_per_video * HEYGEN_USD_PER_CREDIT
    total_per_video = heygen_cost_per_video + CLAUDE_USD_PER_SCRIPT

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "HeyGen (avatar)",
            f"${heygen_cost_per_video:.3f}",
            f"{heygen_credits_per_video} crediti × ${HEYGEN_USD_PER_CREDIT:.3f}",
        )
    with c2:
        st.metric(
            "Claude (script)",
            f"${CLAUDE_USD_PER_SCRIPT:.3f}",
            "~800 in + 250 out tokens",
        )
    with c3:
        st.metric(
            "Totale per video",
            f"${total_per_video:.3f}",
            f"video di {target_duration}s",
        )

    st.info(
        f"**Stima:** ogni reel da {target_duration} secondi costa circa "
        f"**${total_per_video:.2f}** in API."
    )

    st.divider()

    # ── HeyGen balance ──
    st.subheader("🪙 Saldo HeyGen API")

    if credits >= 0:
        remaining_value = credits * HEYGEN_USD_PER_CREDIT
        videos_left = credits // max(1, heygen_credits_per_video)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Crediti rimanenti", f"{credits}")
        with c2:
            st.metric("Valore residuo", f"${remaining_value:.2f}")
        with c3:
            st.metric(
                f"Video da {target_duration}s ancora generabili",
                f"~{videos_left}",
            )
    else:
        st.warning("Impossibile leggere il saldo HeyGen")

    st.divider()

    # ── Usage so far ──
    st.subheader("📊 Utilizzo finora")

    videos_made = _video_count_from_outputs()
    estimated_total_spent = videos_made * total_per_video

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Video generati (locali)", videos_made)
    with c2:
        st.metric("Costo stimato totale", f"${estimated_total_spent:.2f}")

    st.divider()

    # ── Monthly projection ──
    st.subheader("📅 Proiezione mensile")

    scenarios = [
        ("1 reel al giorno", 1),
        ("2 reel al giorno", 2),
        ("3 reel al giorno", 3),
        ("5 reel al giorno", 5),
    ]

    cols = st.columns(len(scenarios))
    for col, (label, per_day) in zip(cols, scenarios):
        with col:
            monthly = per_day * 30 * total_per_video
            st.metric(label, f"${monthly:.2f}/mese", f"{per_day * 30} video")

    st.divider()

    # ── Pricing breakdown ──
    with st.expander("📖 Dettagli prezzi"):
        st.markdown(f"""
        **HeyGen API:**
        - Pacchetto crediti: ~$99 per 1500 crediti
        - Costo per credito: **${HEYGEN_USD_PER_CREDIT:.4f}**
        - Consumo: ~1 credito per secondo di video
        - Per un reel di {target_duration}s: **{heygen_credits_per_video} crediti = ${heygen_cost_per_video:.3f}**

        **Claude API (claude-sonnet-4):**
        - Input: $3 per milione di token
        - Output: $15 per milione di token
        - Per script: ~800 input + 250 output token = **${CLAUDE_USD_PER_SCRIPT:.4f}**

        **Whisper (trascrizione):**
        - Gira in locale, **costo zero** (CPU)

        **Editing video (MoviePy):**
        - Gira in locale, **costo zero**

        **Pubblicazione Instagram (Meta API):**
        - **Gratis**

        **Hosting Railway:**
        - $5-20/mese fissi (a seconda dell'utilizzo)
        """)

    # Stop here so wizard doesn't render
    st.stop()


# ── STEP 1: Avatar & Look ────────────────────────────────────────────────────

if st.session_state.step == 1:
    st.markdown(
        f'<h1 class="pwr-h1" translate="no" lang="it">{STEP_TITLES[1]}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pwr-caption">Scegli il tuo avatar AI e il look perfetto per il tuo reel.</div>',
        unsafe_allow_html=True,
    )

    groups = data["groups"]
    all_looks = data["looks"]
    current_avatar = settings["heygen"]["avatar_id"]

    if not groups:
        st.error("Nessun avatar trovato. Verifica HEYGEN_API_KEY in config/.env")
        st.stop()

    # Determine which group contains the currently-active look
    avatar_names = [g["name"] for g in groups]
    active_group = avatar_names[0]
    for gname, looks in all_looks.items():
        for look in looks:
            if look["look_id"] == current_avatar:
                active_group = gname
                break

    # Persist the user's "browsing" group across reruns (separate from the
    # active/saved one — user might explore another avatar's looks before
    # actually selecting a new look).
    if "wizard_browsing_group" not in st.session_state:
        st.session_state.wizard_browsing_group = active_group
    elif st.session_state.wizard_browsing_group not in avatar_names:
        st.session_state.wizard_browsing_group = active_group

    selected_group = st.session_state.wizard_browsing_group

    # ── Sub-step A: avatar group cards ──
    st.markdown(
        '<div class="pwr-section-label">⚡ Step 1.A · Avatar</div>',
        unsafe_allow_html=True,
    )

    group_cols = st.columns(min(len(groups), 4))
    for idx, g in enumerate(groups):
        gname = g["name"]
        gl = all_looks.get(gname, [])
        preview_img = gl[0]["image_url"] if gl else ""
        is_browsing = gname == selected_group
        is_active = gname == active_group

        with group_cols[idx % 4]:
            klass = "pwr-card" + (" selected" if is_browsing else "")
            active_pill = (
                '<div class="pwr-active-pill">● ATTIVO</div>'
                if is_active else ""
            )
            looks_count = len(gl)
            preview_html = (
                f'<img src="{preview_img}" alt="{gname}">'
                if preview_img
                else '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#52525b;">🎭</div>'
            )
            st.markdown(
                f'<div class="{klass}">'
                f'  <div class="pwr-card-img">{active_pill}{preview_html}</div>'
                f'  <div class="pwr-card-name">{gname}</div>'
                f'  <div class="pwr-card-meta">{looks_count} look disponibil{"i" if looks_count != 1 else "e"}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            btn_label = "✓ In esplorazione" if is_browsing else "Esplora look →"
            if st.button(
                btn_label,
                key=f"grp_{gname}_{idx}",
                use_container_width=True,
                disabled=is_browsing,
                type="primary" if is_browsing else "secondary",
            ):
                st.session_state.wizard_browsing_group = gname
                st.rerun()

    st.divider()

    # ── Sub-step B: look cards for the currently browsing group ──
    looks = all_looks.get(selected_group, [])
    st.markdown(
        '<div class="pwr-section-label">🎬 Step 1.B · Look</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<h3 style="margin:0 0 18px;">Scegli un look per <span style="color:#ff667f;">{selected_group}</span> '
        f'<span style="color:#71717a;font-weight:500;font-size:.9rem;">({len(looks)} disponibil{"i" if len(looks) != 1 else "e"})</span></h3>',
        unsafe_allow_html=True,
    )

    if looks:
        cols = st.columns(min(len(looks), 4))
        for i, look in enumerate(looks):
            with cols[i % 4]:
                is_selected = look["look_id"] == current_avatar
                klass = "pwr-card" + (" selected" if is_selected else "")
                active_pill = (
                    '<div class="pwr-active-pill">✓ ATTIVO</div>'
                    if is_selected else ""
                )
                st.markdown(
                    f'<div class="{klass}">'
                    f'  <div class="pwr-card-img">{active_pill}<img src="{look["image_url"]}" alt="{look["name"]}"></div>'
                    f'  <div class="pwr-card-name">{look["name"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "✓ Selezionato" if is_selected else "Seleziona look",
                    key=f"look_{look['look_id']}",
                    use_container_width=True,
                    disabled=is_selected,
                    type="primary" if is_selected else "secondary",
                ):
                    settings["heygen"]["avatar_id"] = look["look_id"]
                    save_settings(settings)
                    st.rerun()

    st.divider()
    can_proceed = bool(settings["heygen"]["avatar_id"])
    if not can_proceed:
        st.warning("Seleziona un look per proseguire")
    nav_buttons(1, can_proceed)


# ── STEP 2: Voce ─────────────────────────────────────────────────────────────

elif st.session_state.step == 2:
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[2]}</h1>', unsafe_allow_html=True)
    st.caption("Scegli quale voce clonata usare")

    voices = data["voices"]
    current_voice = settings["heygen"]["voice_id"]

    if voices:
        for voice in voices:
            is_selected = voice["voice_id"] == current_voice
            col1, col2, col3 = st.columns([3, 3, 1])
            with col1:
                icon = "✅" if is_selected else "🎙️"
                st.write(f"{icon} **{voice['name']}** — {voice['language']}")
            with col2:
                if voice.get("preview_audio"):
                    st.audio(voice["preview_audio"])
            with col3:
                if not is_selected:
                    if st.button("Usa", key=f"vc_{voice['voice_id']}", use_container_width=True):
                        settings["heygen"]["voice_id"] = voice["voice_id"]
                        save_settings(settings)
                        st.rerun()
    else:
        st.warning("Nessuna voce custom trovata")

    st.divider()
    nav_buttons(2, bool(settings["heygen"]["voice_id"]))


# ── STEP 3: Fonti Notizie ────────────────────────────────────────────────────

elif st.session_state.step == 3:
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[3]}</h1>', unsafe_allow_html=True)
    st.caption("I siti RSS da cui prendere le notizie per generare lo script")

    feeds = settings["scraper"]["feeds"]

    for i, feed in enumerate(feeds):
        col1, col2, col3, col4 = st.columns([3, 5, 1, 1])
        with col1:
            feeds[i]["name"] = st.text_input("Nome", feed["name"], key=f"fn_{i}", label_visibility="collapsed")
        with col2:
            feeds[i]["url"] = st.text_input("URL", feed["url"], key=f"fu_{i}", label_visibility="collapsed")
        with col3:
            feeds[i]["lang"] = st.selectbox("Lang", ["it", "en"],
                index=0 if feed["lang"] == "it" else 1,
                key=f"fl_{i}", label_visibility="collapsed")
        with col4:
            if st.button("🗑️", key=f"del_{i}"):
                feeds.pop(i)
                settings["scraper"]["feeds"] = feeds
                save_settings(settings)
                st.rerun()

    st.divider()
    st.subheader("Aggiungi nuovo feed")
    with st.form("add_feed", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 5, 2])
        with c1:
            new_name = st.text_input("Nome", "")
        with c2:
            new_url = st.text_input("URL RSS", "")
        with c3:
            new_lang = st.selectbox("Lingua", ["it", "en"])
        if st.form_submit_button("➕ Aggiungi"):
            if new_name and new_url:
                feeds.append({"name": new_name, "url": new_url, "lang": new_lang})
                settings["scraper"]["feeds"] = feeds
                save_settings(settings)
                st.rerun()

    if st.button("💾 Salva modifiche", type="secondary"):
        save_settings(settings)
        st.success("Salvato")

    st.divider()
    nav_buttons(3, len(feeds) > 0)


# ── STEP 4: Script & Tono ────────────────────────────────────────────────────

elif st.session_state.step == 4:
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[4]}</h1>', unsafe_allow_html=True)
    st.caption("Come Claude scrive lo script del reel")

    col1, col2 = st.columns(2)
    with col1:
        settings["scriptwriter"]["target_duration_seconds"] = st.slider(
            "Durata video (secondi)", 15, 90,
            settings["scriptwriter"]["target_duration_seconds"],
        )
    with col2:
        settings["scriptwriter"]["tone"] = st.text_input(
            "Tono", settings["scriptwriter"]["tone"],
        )

    settings["scriptwriter"]["system_prompt"] = st.text_area(
        "Istruzioni per Claude (system prompt)",
        settings["scriptwriter"]["system_prompt"], height=250,
    )
    st.caption("Variabili: `{duration}`, `{tone}`, `{word_count}`")

    if st.button("💾 Salva", type="secondary"):
        save_settings(settings)
        st.success("Salvato")

    st.divider()
    nav_buttons(4, True)


# ── STEP 5: Stile Sottotitoli ────────────────────────────────────────────────

elif st.session_state.step == 5:
    import base64

    st.markdown(
        f'<h1 class="pwr-h1" translate="no" lang="it">{STEP_TITLES[5]}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pwr-caption">Scegli lo stile dei sottotitoli karaoke. Ogni preset mostra come apparirà davvero nel tuo reel.</div>',
        unsafe_allow_html=True,
    )

    from src.subtitle_presets import PRESETS

    current_preset = settings["editor"]["subtitle"].get("preset", "classic")
    using_heygen = settings["heygen"].get("subtitle_source") == "heygen"

    def _img_data_url(path):
        """Inline a local PNG as base64 data URL (so it renders inside the card markdown)."""
        try:
            return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        except Exception:
            return ""

    # ── PRESET CARDS ──
    st.markdown(
        '<div class="pwr-section-label">🎬 Step 5 · Stile sottotitoli</div>',
        unsafe_allow_html=True,
    )

    preset_ids = list(PRESETS.keys())
    cols = st.columns(len(preset_ids))

    for i, pid in enumerate(preset_ids):
        preset = PRESETS[pid]
        with cols[i]:
            is_selected = (pid == current_preset) and not using_heygen
            klass = "pwr-card" + (" selected" if is_selected else "")
            active_pill = (
                '<div class="pwr-active-pill">✓ ATTIVO</div>'
                if is_selected else ""
            )
            preview_path = PROJECT_ROOT / "assets" / "templates" / f"preset_{pid}.png"
            data_url = _img_data_url(preview_path) if preview_path.exists() else ""
            preview_html = (
                f'<img src="{data_url}" alt="{preset["name"]}">'
                if data_url
                else '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#52525b;">📝 Preview non disponibile</div>'
            )
            st.markdown(
                f'<div class="{klass}">'
                f'  <div class="pwr-card-img wide">{active_pill}{preview_html}</div>'
                f'  <div class="pwr-card-name">{preset["name"]}</div>'
                f'  <div class="pwr-card-meta">{preset["description"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "✓ Selezionato" if is_selected else "Seleziona stile",
                key=f"preset_{pid}",
                use_container_width=True,
                disabled=is_selected,
                type="primary" if is_selected else "secondary",
            ):
                new_settings = dict(preset["settings"])
                new_settings["preset"] = pid
                new_settings["position"] = settings["editor"]["subtitle"].get("position", "center")
                new_settings["max_chars_per_line"] = settings["editor"]["subtitle"].get("max_chars_per_line", 25)
                settings["editor"]["subtitle"] = new_settings
                settings["heygen"]["subtitle_source"] = "custom"
                settings["heygen"]["caption"] = False
                save_settings(settings)
                st.rerun()

    st.divider()

    # ── ALTERNATIVE: HeyGen built-in (same card style, single column) ──
    st.markdown(
        '<div class="pwr-section-label">⚙️ Alternativa · Sottotitoli HeyGen</div>',
        unsafe_allow_html=True,
    )
    hg_col, _spacer1, _spacer2, _spacer3 = st.columns(4)
    with hg_col:
        klass = "pwr-card" + (" selected" if using_heygen else "")
        active_pill = '<div class="pwr-active-pill">✓ ATTIVO</div>' if using_heygen else ""
        hp = PROJECT_ROOT / "assets" / "templates" / "heygen_caption_preview.png"
        hg_data_url = _img_data_url(hp) if hp.exists() else ""
        preview_html = (
            f'<img src="{hg_data_url}" alt="HeyGen">'
            if hg_data_url
            else '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#52525b;">⚙️</div>'
        )
        st.markdown(
            f'<div class="{klass}">'
            f'  <div class="pwr-card-img wide">{active_pill}{preview_html}</div>'
            f'  <div class="pwr-card-name">HeyGen Built-in</div>'
            f'  <div class="pwr-card-meta">Sottotitoli classici bianchi generati da HeyGen, no karaoke</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if using_heygen:
            if st.button("✓ Selezionato", key="hg_active", use_container_width=True, disabled=True, type="primary"):
                pass
        else:
            if st.button("Seleziona stile", key="hg_use", use_container_width=True):
                settings["heygen"]["subtitle_source"] = "heygen"
                settings["heygen"]["caption"] = True
                save_settings(settings)
                st.rerun()

    st.divider()

    # ── CUSTOMIZATION (only if Custom preset is active) ──
    if settings["heygen"].get("subtitle_source", "custom") == "custom":
        with st.expander("🎨 Personalizzazione avanzata", expanded=False):
            sub = settings["editor"]["subtitle"]

            font_options = {
                "Bebas Neue (condensed bold)": "./assets/fonts/BebasNeue-Regular.ttf",
                "Montserrat Bold": "./assets/fonts/Montserrat-Bold.ttf",
            }
            current_font = next(
                (k for k, v in font_options.items() if v == sub.get("font_path")),
                list(font_options.keys())[0],
            )
            chosen_font = st.selectbox(
                "Font", list(font_options.keys()),
                index=list(font_options.keys()).index(current_font),
            )
            sub["font_path"] = font_options[chosen_font]

            c1, c2 = st.columns(2)
            with c1:
                sub["font_size"] = st.slider("Dimensione testo", 30, 130, sub.get("font_size", 90))
                sub["words_per_subtitle"] = st.slider("Parole per frase", 2, 6, sub.get("words_per_subtitle", 3))
                sub["stroke_width"] = st.slider("Spessore bordo", 1, 10, sub.get("stroke_width", 5))
                sub["uppercase"] = st.toggle("TUTTO MAIUSCOLO", sub.get("uppercase", True))
                sub["add_emoji"] = st.toggle("Aggiungi emoji contestuale", sub.get("add_emoji", False))
            with c2:
                sub["font_color"] = st.color_picker("Colore testo", sub.get("font_color", "#FFFFFF"))
                sub["accent_color"] = st.color_picker("Colore evidenziazione", sub.get("accent_color", "#E8163C"))
                sub["stroke_color"] = st.color_picker("Colore bordo", sub.get("stroke_color", "#000000"))

                hl_options = {
                    "Box colorato dietro la parola": "box",
                    "Solo cambio colore parola": "color",
                    "Nessuna evidenziazione": "none",
                }
                current_hl = next(
                    (k for k, v in hl_options.items() if v == sub.get("highlight_style", "box")),
                    list(hl_options.keys())[0],
                )
                chosen_hl = st.selectbox(
                    "Tipo evidenziazione", list(hl_options.keys()),
                    index=list(hl_options.keys()).index(current_hl),
                )
                sub["highlight_style"] = hl_options[chosen_hl]

            settings["editor"]["subtitle"] = sub

            if st.button("💾 Salva personalizzazione", type="primary"):
                save_settings(settings)
                st.success("✅ Salvato — il prossimo reel userà questo stile")

    st.divider()
    nav_buttons(5, True)


# ── STEP 6: Instagram ────────────────────────────────────────────────────────

elif st.session_state.step == 6:
    st.markdown(
        f'<h1 class="pwr-h1" translate="no" lang="it">{STEP_TITLES[6]}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pwr-caption">Scegli su quali account pubblicare. Selezionane uno o tutti — un click pubblica ovunque.</div>',
        unsafe_allow_html=True,
    )

    publisher_cfg = settings.setdefault("publisher", {})
    enabled = publisher_cfg.get("enabled_platforms", ["instagram"])

    user_profile = _users.get_user(st.session_state.user_email) or {}
    user_keys = user_profile.get("api_keys", {})
    meta_pages = user_keys.get("meta_pages", [])

    # Back-compat: if no meta_pages list yet, build a synthetic one from legacy fields
    if not meta_pages:
        legacy_fb = user_keys.get("facebook_page_id", "")
        legacy_ig = user_keys.get("instagram_business_account_id", "")
        if legacy_fb or legacy_ig:
            meta_pages = [{
                "page_id": legacy_fb,
                "page_name": user_keys.get("facebook_page_name", "") or "Facebook Page",
                "page_access_token": user_keys.get("facebook_page_access_token", ""),
                "instagram_business_account_id": legacy_ig,
                "instagram_username": user_keys.get("instagram_username", ""),
            }]

    # First-visit default: auto-select all available pages so the user can
    # proceed without clicking on every card. They can deselect from the UI.
    if "selected_pages" not in publisher_cfg and meta_pages:
        publisher_cfg["selected_pages"] = [p["page_id"] for p in meta_pages]
        save_settings(settings)
    selected_page_ids = set(publisher_cfg.get("selected_pages", []))

    # ── Account cards ──
    st.markdown(
        '<div class="pwr-section-label">📡 Step 6 · Account collegati</div>',
        unsafe_allow_html=True,
    )

    if not meta_pages:
        st.warning(
            "Nessun account collegato. Vai su **🔑 Configura API Keys → Collega Facebook** "
            "per autorizzare le tue Pagine FB e gli account Instagram Business."
        )
    else:
        # Quick action toolbar — select all / none
        tool_cols = st.columns([1, 1, 6])
        with tool_cols[0]:
            if st.button("✓ Tutti", key="sel_all", use_container_width=True):
                selected_page_ids = {p["page_id"] for p in meta_pages}
                publisher_cfg["selected_pages"] = list(selected_page_ids)
                save_settings(settings)
                st.rerun()
        with tool_cols[1]:
            if st.button("✗ Nessuno", key="sel_none", use_container_width=True):
                selected_page_ids = set()
                publisher_cfg["selected_pages"] = []
                save_settings(settings)
                st.rerun()
        with tool_cols[2]:
            n_sel = len(selected_page_ids & {p["page_id"] for p in meta_pages})
            st.markdown(
                f'<div style="padding:10px 4px; color:#a1a1aa; font-size:.9rem;">'
                f'<b style="color:#fafafa;">{n_sel}</b> di <b>{len(meta_pages)}</b> account selezionat{"i" if n_sel != 1 else "o"} per la pubblicazione'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Per-page cards
        cols_per_row = 4
        for row_start in range(0, len(meta_pages), cols_per_row):
            row_pages = meta_pages[row_start:row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for i, page in enumerate(row_pages):
                with cols[i]:
                    pid = page["page_id"]
                    is_selected = pid in selected_page_ids
                    has_ig = bool(page.get("instagram_business_account_id"))
                    klass = "pwr-card pwr-account-card" + (" selected" if is_selected else "")
                    active_pill = '<div class="pwr-active-pill">✓ ATTIVO</div>' if is_selected else ""

                    # Inline SVG icons (Instagram + Facebook). Pure CSS gradient backgrounds.
                    ig_icon = (
                        '<div class="pwr-acct-icon ig"><svg viewBox="0 0 24 24" fill="white" width="22" height="22">'
                        '<path d="M12 2.2c3.2 0 3.6 0 4.8.1 1.2.1 1.8.2 2.2.4.6.2 1 .5 1.4.9.4.4.7.8.9 1.4.2.4.4 1 .4 2.2.1 1.2.1 1.6.1 4.8s0 3.6-.1 4.8c-.1 1.2-.2 1.8-.4 2.2-.2.6-.5 1-.9 1.4-.4.4-.8.7-1.4.9-.4.2-1 .4-2.2.4-1.2.1-1.6.1-4.8.1s-3.6 0-4.8-.1c-1.2-.1-1.8-.2-2.2-.4-.6-.2-1-.5-1.4-.9-.4-.4-.7-.8-.9-1.4-.2-.4-.4-1-.4-2.2-.1-1.2-.1-1.6-.1-4.8s0-3.6.1-4.8c.1-1.2.2-1.8.4-2.2.2-.6.5-1 .9-1.4.4-.4.8-.7 1.4-.9.4-.2 1-.4 2.2-.4 1.2-.1 1.6-.1 4.8-.1zm0 2c-3.2 0-3.5 0-4.7.1-1 .1-1.5.2-1.9.3-.5.2-.8.4-1.2.7-.3.3-.6.7-.7 1.2-.1.4-.3.9-.3 1.9-.1 1.2-.1 1.5-.1 4.7s0 3.5.1 4.7c.1 1 .2 1.5.3 1.9.2.5.4.8.7 1.2.3.3.7.6 1.2.7.4.1.9.3 1.9.3 1.2.1 1.5.1 4.7.1s3.5 0 4.7-.1c1-.1 1.5-.2 1.9-.3.5-.2.8-.4 1.2-.7.3-.3.6-.7.7-1.2.1-.4.3-.9.3-1.9.1-1.2.1-1.5.1-4.7s0-3.5-.1-4.7c-.1-1-.2-1.5-.3-1.9-.2-.5-.4-.8-.7-1.2-.3-.3-.7-.6-1.2-.7-.4-.1-.9-.3-1.9-.3-1.2-.1-1.5-.1-4.7-.1zm0 3.4a4.4 4.4 0 110 8.8 4.4 4.4 0 010-8.8zm0 7.3a2.9 2.9 0 100-5.8 2.9 2.9 0 000 5.8zm5.6-7.5a1 1 0 110 2 1 1 0 010-2z"/>'
                        '</svg></div>'
                    )
                    fb_icon = (
                        '<div class="pwr-acct-icon fb"><svg viewBox="0 0 24 24" fill="white" width="22" height="22">'
                        '<path d="M22 12a10 10 0 10-11.6 9.9V14.9H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.3c-1.2 0-1.6.8-1.6 1.6V12h2.7l-.4 2.9h-2.3V22A10 10 0 0022 12z"/>'
                        '</svg></div>'
                    )

                    # Compose icon row: always show FB; show IG as a smaller chip if linked
                    icon_block = (
                        f'<div class="pwr-acct-icon-row">{fb_icon}'
                        f'{ig_icon if has_ig else ""}'
                        f'</div>'
                    )

                    fb_label = page.get("page_name") or page["page_id"]
                    ig_label = (
                        f'<div class="pwr-acct-ig-label">@{page["instagram_username"] or "ig"}</div>'
                        if has_ig else
                        '<div class="pwr-acct-ig-label muted">Solo Facebook (no IG)</div>'
                    )

                    st.markdown(
                        f'<div class="{klass}">'
                        f'  <div class="pwr-acct-banner">{active_pill}{icon_block}</div>'
                        f'  <div class="pwr-card-name">{fb_label}</div>'
                        f'  <div class="pwr-card-meta">{ig_label}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    btn_label = "✓ Pubblica qui" if is_selected else "Attiva pubblicazione"
                    if st.button(
                        btn_label,
                        key=f"page_toggle_{pid}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                    ):
                        if is_selected:
                            selected_page_ids.discard(pid)
                        else:
                            selected_page_ids.add(pid)
                        publisher_cfg["selected_pages"] = list(selected_page_ids)
                        save_settings(settings)
                        st.rerun()

    # Save derived enabled_platforms (compat with existing pipeline) + selected_pages
    has_ig_selected = any(
        p["page_id"] in selected_page_ids and p.get("instagram_business_account_id")
        for p in meta_pages
    )
    has_fb_selected = any(p["page_id"] in selected_page_ids for p in meta_pages)
    new_enabled = []
    if has_ig_selected:
        new_enabled.append("instagram")
    if has_fb_selected:
        new_enabled.append("facebook")
    publisher_cfg["enabled_platforms"] = new_enabled

    st.divider()

    # ── Caption template ──
    st.markdown(
        '<div class="pwr-section-label">📝 Caption del reel</div>',
        unsafe_allow_html=True,
    )
    publisher_cfg["caption_template"] = st.text_area(
        "Template Caption (usa {summary_bullets} per le notizie)",
        publisher_cfg.get("caption_template", ""), height=180,
        label_visibility="visible",
    )
    st.caption("La stessa caption viene usata per tutti gli account selezionati.")

    if st.button("💾 Salva caption", type="secondary"):
        save_settings(settings)
        st.success("Salvato")

    st.divider()
    can_proceed = len(selected_page_ids) > 0
    if not can_proceed:
        st.warning("Seleziona almeno un account per proseguire")
    nav_buttons(6, can_proceed)


# ── STEP 7: Genera & Pubblica ────────────────────────────────────────────────

elif st.session_state.step == 7:
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[7]}</h1>', unsafe_allow_html=True)
    st.caption("Genera il reel e pubblicalo su Instagram")

    today = date.today().isoformat()
    run_dir = PROJECT_ROOT / "output" / today
    final_path = run_dir / "final.mp4"
    script_path = run_dir / "script.txt"
    avatar_raw_path = run_dir / "avatar_raw.mp4"

    # ── MODE TOGGLE ──
    st.subheader("⚙️ Modalità di generazione")
    mode_col1, mode_col2 = st.columns(2)

    current_mode = settings.get("generation_mode", "api")

    with mode_col1:
        is_api = current_mode == "api"
        border = "3px solid #E8163C" if is_api else "1px solid #444"
        st.markdown(
            f'<div style="border:{border}; border-radius:12px; padding:12px;">'
            f'<h4 style="margin:0;">🤖 Pieno Automatico (API)</h4>'
            f'<p style="margin:4px 0; font-size:13px; color:#aaa;">'
            f'Tutto in 1 click. POWEREEL chiama HeyGen API. <b>Costo: ~$3 a video</b>'
            f'</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("✅ Attivo" if is_api else "Usa modalità API", key="m_api",
                     use_container_width=True, disabled=is_api):
            settings["generation_mode"] = "api"
            save_settings(settings)
            st.rerun()

    with mode_col2:
        is_manual = current_mode == "manual"
        border = "3px solid #E8163C" if is_manual else "1px solid #444"
        st.markdown(
            f'<div style="border:{border}; border-radius:12px; padding:12px;">'
            f'<h4 style="margin:0;">✋ Semi-Manuale (HeyGen Dashboard)</h4>'
            f'<p style="margin:4px 0; font-size:13px; color:#aaa;">'
            f'3 click in più: generi avatar su HeyGen.com (crediti del piano). <b>Costo: $0</b>'
            f'</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("✅ Attivo" if is_manual else "Usa modalità Manuale", key="m_man",
                     use_container_width=True, disabled=is_manual):
            settings["generation_mode"] = "manual"
            save_settings(settings)
            st.rerun()

    st.divider()

    with st.expander("📋 Riepilogo configurazione", expanded=False):
        st.write(f"**Avatar/Look:** `{settings['heygen']['avatar_id'][:16]}...`")
        st.write(f"**Voce:** `{settings['heygen']['voice_id'][:16]}...`")
        st.write(f"**Feed:** {len(settings['scraper']['feeds'])} attivi")
        st.write(f"**Durata:** {settings['scriptwriter']['target_duration_seconds']}s")
        st.write(f"**Preset sottotitoli:** {settings['editor']['subtitle'].get('preset', 'classic')}")

    st.divider()

    # ── MODE: API (full automatic) ──
    if current_mode == "api":
        st.subheader("▶️ Genera reel automatico")

        running = is_generation_running()
        if running:
            elapsed = int(time.time() - get_generation_started_at())
            st.info(f"⏳ Generazione in corso... ({elapsed}s) — può impiegare 5-8 minuti")
            st.progress(min(elapsed / 480, 0.95))
            log_path = PROJECT_ROOT / "logs" / "wizard_run.log"
            if log_path.exists():
                with st.expander("📜 Log live", expanded=True):
                    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    st.code("\n".join(lines[-20:]))
            time.sleep(5)
            st.rerun()
        else:
            result = get_generation_result()
            if result == "ok":
                st.success("✅ Generazione completata!")
            elif result and result.startswith("error"):
                st.error(f"❌ {result}")

            col_g, col_v = st.columns(2)
            with col_g:
                if st.button("▶️ Genera Reel (anteprima)", type="primary", use_container_width=True):
                    run_pipeline_background(dry_run=True)
                    st.rerun()
            with col_v:
                if st.button("🔄 Rigenera", use_container_width=True, disabled=not final_path.exists()):
                    run_pipeline_background(dry_run=True)
                    st.rerun()

    # ── MODE: MANUAL (semi-manual) ──
    else:
        st.subheader("✋ Generazione semi-manuale")
        st.markdown("""
        **Come funziona:**
        1. Clicca **"Genera Script"** → POWEREEL crea lo script con Claude
        2. Copia lo script, vai su HeyGen.com, seleziona l'avatar e incolla lo script
        3. Clicca **Generate** su HeyGen → aspetta 2 min → scarica il video MP4
        4. Carica il video MP4 qui sotto
        5. POWEREEL aggiunge sottotitoli karaoke + tutto il resto
        6. Pubblica su Instagram
        """)

        st.divider()

        # Step manual A: Generate script
        st.markdown("### 1️⃣ Genera lo script")
        if st.button("📝 Genera Script con Claude", type="primary"):
            with st.spinner("Sto generando lo script..."):
                try:
                    from src.config_loader import load_config
                    from src.scraper import scrape_news, save_articles
                    from src.scriptwriter import generate_script, save_script

                    cfg = load_config(check_ffmpeg=False)
                    run_dir.mkdir(parents=True, exist_ok=True)
                    articles = scrape_news(cfg.scraper)
                    save_articles(articles, run_dir)
                    script = generate_script(articles, cfg.scriptwriter, cfg.anthropic_api_key)
                    save_script(script, run_dir)
                    st.success("✅ Script pronto!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")

        if script_path.exists():
            script_text = script_path.read_text(encoding="utf-8")
            st.markdown("### 2️⃣ Copia lo script e portalo su HeyGen")
            st.text_area("Script generato (selezionalo e copia con Ctrl+C)",
                         script_text, height=180, key="script_display")

            st.markdown(
                '<a href="https://app.heygen.com" target="_blank" rel="noopener noreferrer" '
                'style="display:block; padding:14px; background:#E8163C; color:white; '
                'text-align:center; border-radius:8px; text-decoration:none; font-weight:bold; '
                'font-size:16px;">🚀 Apri HeyGen Dashboard</a>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Una volta aperta HeyGen, vai su **Avatar** o **Quick Create**, "
                "seleziona l'avatar/look e incolla lo script qui sopra."
            )

            # Show user which avatar/voice to use - find the friendly name
            current_avatar_id = settings["heygen"]["avatar_id"]
            avatar_name = "?"
            look_name = "?"
            for gname, looks in data["looks"].items():
                for look in looks:
                    if look["look_id"] == current_avatar_id:
                        avatar_name = gname
                        look_name = look["name"]
                        break
            voice_name = "?"
            for v in data["voices"]:
                if v["voice_id"] == settings["heygen"]["voice_id"]:
                    voice_name = f"{v['name']} ({v['language']})"
                    break

            st.info(
                f"📌 **Su HeyGen seleziona:**\n\n"
                f"- **Avatar:** {avatar_name} → look **{look_name}**\n"
                f"- **Voce:** {voice_name}"
            )

            st.divider()
            st.markdown("### 3️⃣ Carica il video MP4 scaricato da HeyGen")

            tab1, tab2 = st.tabs(["📁 Upload file", "🔗 Incolla URL (consigliato per file grandi)"])

            with tab1:
                uploaded = st.file_uploader("Trascina qui il file MP4", type=["mp4", "mov"])
                if uploaded is not None:
                    try:
                        avatar_raw_path.parent.mkdir(parents=True, exist_ok=True)
                        avatar_raw_path.write_bytes(uploaded.read())
                        st.success(f"✅ Video caricato ({avatar_raw_path.stat().st_size / 1024 / 1024:.1f} MB)")
                    except Exception as e:
                        st.error(f"Errore upload: {e}")

            with tab2:
                st.caption(
                    "Su HeyGen, dopo aver generato il video, **clicca destro sul bottone Download** "
                    "e seleziona **'Copia indirizzo link'**. Poi incollalo qui sotto."
                )
                video_url = st.text_input("URL del video MP4", key="video_url_input")
                if st.button("⬇️ Scarica video da URL", type="primary"):
                    if video_url:
                        try:
                            import httpx as _httpx
                            with st.spinner("Download in corso..."):
                                avatar_raw_path.parent.mkdir(parents=True, exist_ok=True)
                                with _httpx.stream("GET", video_url, timeout=180,
                                                    follow_redirects=True) as resp:
                                    resp.raise_for_status()
                                    with open(avatar_raw_path, "wb") as f:
                                        for chunk in resp.iter_bytes(chunk_size=65536):
                                            f.write(chunk)
                            st.success(f"✅ Scaricato ({avatar_raw_path.stat().st_size / 1024 / 1024:.1f} MB)")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore download: {e}")
                    else:
                        st.warning("Incolla un URL valido")

            if avatar_raw_path.exists():
                st.video(str(avatar_raw_path))

            if avatar_raw_path.exists():
                st.divider()
                st.markdown("### 4️⃣ Aggiungi sottotitoli karaoke")
                running = is_generation_running()
                result = get_generation_result()

                if result and result.startswith("error"):
                    st.error(f"❌ Ultima esecuzione: {result}")

                if running:
                    elapsed = int(time.time() - get_generation_started_at())
                    st.info(f"⏳ Editing in corso... ({elapsed}s) — di solito 2-4 min")
                    st.progress(min(elapsed / 240, 0.95))
                    log_path = PROJECT_ROOT / "logs" / "wizard_run.log"
                    if log_path.exists():
                        with st.expander("📜 Log live", expanded=False):
                            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                            st.code("\n".join(lines[-15:]))
                    cstop, _ = st.columns([1, 3])
                    with cstop:
                        if st.button("🛑 Annulla", key="abort_edit"):
                            if RUN_MARKER.exists():
                                RUN_MARKER.unlink()
                            DONE_MARKER.write_text("error: annullato manualmente")
                            st.rerun()
                    time.sleep(3)
                    st.rerun()
                else:
                    if st.button("🎨 Avvia editing (sottotitoli + sync)",
                                 type="primary", use_container_width=True):
                        # Run only editor stage on the uploaded video
                        def _editor_only():
                            log = PROJECT_ROOT / "logs" / "wizard_run.log"
                            if DONE_MARKER.exists():
                                DONE_MARKER.unlink()
                            RUN_MARKER.write_text(str(time.time()))
                            wrapper = (
                                "import traceback\n"
                                "from pathlib import Path\n"
                                f"DONE = Path(r'{DONE_MARKER}')\n"
                                f"LOCK = Path(r'{RUN_MARKER}')\n"
                                "try:\n"
                                "    from src.config_loader import load_config\n"
                                "    from src.scriptwriter import load_script\n"
                                "    from src.editor import edit_video\n"
                                "    cfg = load_config(check_ffmpeg=False)\n"
                                f"    rd = Path(r'{run_dir}')\n"
                                "    script = load_script(rd)\n"
                                "    edit_video(rd / 'avatar_raw.mp4', script, cfg.editor, rd)\n"
                                "    DONE.write_text('ok')\n"
                                "except Exception as e:\n"
                                "    err_msg = f'error: {type(e).__name__}: {e}'\n"
                                "    print(err_msg)\n"
                                "    print(traceback.format_exc())\n"
                                "    DONE.write_text(err_msg)\n"
                                "finally:\n"
                                "    if LOCK.exists(): LOCK.unlink()\n"
                            )
                            try:
                                with open(log, "w", encoding="utf-8") as logf:
                                    subprocess.run(
                                        [sys.executable, "-c", wrapper],
                                        stdout=logf, stderr=subprocess.STDOUT,
                                        cwd=str(PROJECT_ROOT), timeout=1200,
                                    )
                            except subprocess.TimeoutExpired:
                                # Subprocess hung — clean up
                                if not DONE_MARKER.exists():
                                    DONE_MARKER.write_text("error: timeout (>20 min)")
                            except Exception as e:
                                if not DONE_MARKER.exists():
                                    DONE_MARKER.write_text(f"error: launcher failed: {e}")
                            finally:
                                # Always cleanup LOCK to avoid stuck state
                                if RUN_MARKER.exists():
                                    RUN_MARKER.unlink()

                        threading.Thread(target=_editor_only, daemon=True).start()
                        st.rerun()

    # ── COMMON: Show last result + publish ──
    if final_path.exists() and not is_generation_running():
        st.divider()
        st.subheader("🎬 Anteprima finale")

        col_l, col_v, col_r = st.columns([1, 1, 2])
        with col_v:
            st.video(str(final_path))

        st.divider()
        st.subheader("📤 Pubblicazione")

        platforms = settings.get("publisher", {}).get("enabled_platforms", ["instagram"])
        if not platforms:
            st.warning("Nessuna piattaforma selezionata — torna allo Step 6.")
        else:
            label = "📤 Pubblica su " + " + ".join(
                {"instagram": "Instagram", "facebook": "Facebook"}[p]
                for p in platforms if p in ("instagram", "facebook")
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button(label, type="primary", use_container_width=True):
                    with st.spinner("Pubblicazione in corso..."):
                        try:
                            from src.config_loader import load_config
                            from src.scraper import load_articles
                            from src.auth import check_and_refresh_token

                            cfg = load_config(check_ffmpeg=False)
                            articles = load_articles(run_dir)
                            token = check_and_refresh_token(
                                cfg.meta_access_token, cfg.meta_app_id, cfg.meta_app_secret
                            )

                            results = {}
                            if "instagram" in platforms:
                                try:
                                    from src.publishers.instagram import publish_to_instagram
                                    media_id = publish_to_instagram(
                                        final_path, articles, cfg.publisher,
                                        cfg.instagram_business_account_id, token,
                                    )
                                    results["instagram"] = media_id
                                    st.success(f"✅ Instagram: {media_id}")
                                except Exception as e:
                                    results["instagram"] = f"error: {e}"
                                    st.error(f"❌ Instagram: {e}")

                            if "facebook" in platforms:
                                try:
                                    from src.publishers.facebook import publish_to_facebook
                                    fb_id = publish_to_facebook(
                                        final_path, articles, cfg.publisher,
                                        cfg.facebook_page_id, token,
                                        page_access_token=cfg.facebook_page_access_token,
                                    )
                                    results["facebook"] = fb_id
                                    st.success(f"✅ Facebook: {fb_id}")
                                except Exception as e:
                                    results["facebook"] = f"error: {e}"
                                    st.error(f"❌ Facebook: {e}")
                        except Exception as e:
                            st.error(f"Errore: {e}")
            with col2:
                st.caption(
                    "Il video viene pubblicato su tutte le piattaforme attive. "
                    "Se una fallisce, le altre continuano."
                )

    nav_buttons(7, True, next_label="Fine")
