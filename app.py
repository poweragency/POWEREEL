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
                     "APP_PASSWORD"]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except Exception:
    pass


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
        <h3>📱 Pubblicazione Instagram</h3>
        <p>Reel pubblicati direttamente sul tuo account Instagram Business via Meta Graph API.
        Anche programmati ogni giorno.</p>
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

    # ── Login form ──
    st.markdown("### 🔒 Accedi al pannello")
    cl1, cl2 = st.columns([2, 3])
    with cl1:
        password = st.text_input("Password", type="password",
                                  placeholder="Inserisci la password")
        if st.button("Accedi →", type="primary", use_container_width=True):
            if password == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Password errata")
    with cl2:
        st.info(
            "Per ottenere l'accesso scrivi a **info@poweragency.it**\n\n"
            "POWEREEL è in fase di beta privata — accesso solo su invito."
        )

    return False


def logout():
    """Clear authentication and reset to landing."""
    st.session_state.authenticated = False
    st.session_state.step = 1
    st.session_state.view = "wizard"
    st.rerun()


if not show_landing_and_login():
    st.stop()


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
def get_heygen_data() -> dict:
    """Get HeyGen avatars filtered to ONLY vertical/Reel format (9:16)."""
    from PIL import Image
    from io import BytesIO

    api_key = os.getenv("HEYGEN_API_KEY", "")
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


@st.cache_data(ttl=120)
def get_heygen_credits() -> int:
    api_key = os.getenv("HEYGEN_API_KEY", "")
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
    "6. Instagram",
    "7. Genera e Pubblica",
]

STEP_TITLES = {
    1: "Passo 1 — Avatar e Look",
    2: "Passo 2 — Voce",
    3: "Passo 3 — Fonti Notizie",
    4: "Passo 4 — Script e Tono",
    5: "Passo 5 — Stile Sottotitoli",
    6: "Passo 6 — Instagram",
    7: "Passo 7 — Genera e Pubblica",
}


# ── Top bar (logout) ──
render_top_bar()


# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("⚡ POWEREEL")
st.sidebar.caption("Wizard step-by-step")

credits = get_heygen_credits()
if credits >= 0:
    st.sidebar.metric("Crediti HeyGen API", credits)
    remaining_value = credits * HEYGEN_USD_PER_CREDIT
    st.sidebar.caption(f"≈ ${remaining_value:.2f} rimasti")

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

    if st.sidebar.button("💰 Centro Costi (Admin)", use_container_width=True):
        st.session_state.view = "costs"
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
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[1]}</h1>', unsafe_allow_html=True)
    st.caption("Scegli quale dei tuoi avatar usare e quale look (outfit/scenario)")

    groups = data["groups"]
    all_looks = data["looks"]
    current_avatar = settings["heygen"]["avatar_id"]

    if not groups:
        st.error("Nessun avatar trovato. Verifica HEYGEN_API_KEY in config/.env")
        st.stop()

    # Sub-step A: choose avatar
    avatar_names = [g["name"] for g in groups]
    current_group = avatar_names[0]
    for gname, looks in all_looks.items():
        for look in looks:
            if look["look_id"] == current_avatar:
                current_group = gname
                break

    selected_group = st.radio(
        "Avatar",
        avatar_names,
        index=avatar_names.index(current_group) if current_group in avatar_names else 0,
        horizontal=True,
    )

    st.divider()
    st.subheader(f"Look disponibili per {selected_group}")

    looks = all_looks.get(selected_group, [])
    if looks:
        cols = st.columns(min(len(looks), 4))
        for i, look in enumerate(looks):
            with cols[i % 4]:
                is_selected = look["look_id"] == current_avatar
                border = "3px solid #E8163C" if is_selected else "1px solid #444"
                st.markdown(
                    f'<div style="border:{border}; border-radius:10px; padding:6px; text-align:center;">'
                    f'<img src="{look["image_url"]}" style="width:100%; border-radius:8px; max-height:180px; object-fit:cover;">'
                    f'<p style="margin:4px 0; font-size:12px;">{look["name"]}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "✅ Attivo" if is_selected else "Usa",
                    key=f"look_{look['look_id']}",
                    use_container_width=True,
                    disabled=is_selected,
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
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[5]}</h1>', unsafe_allow_html=True)
    st.caption("Scegli un preset o personalizza completamente lo stile dei sottotitoli")

    from src.subtitle_presets import PRESETS

    current_preset = settings["editor"]["subtitle"].get("preset", "classic")

    # ── PRESET CARDS ──
    st.subheader("📦 Preset disponibili")

    preset_ids = list(PRESETS.keys())
    cols = st.columns(len(preset_ids))

    for i, pid in enumerate(preset_ids):
        preset = PRESETS[pid]
        with cols[i]:
            is_selected = pid == current_preset
            border = "3px solid #E8163C" if is_selected else "1px solid #444"
            badge = "✅ ATTIVO" if is_selected else ""

            st.markdown(
                f'<div style="border:{border}; border-radius:12px; padding:8px; text-align:center; background:#1a1a2e;">'
                f'<h4 style="margin:4px 0;">{preset["name"]}</h4>'
                f'<p style="margin:0 0 6px; font-size:11px; color:#888;">{preset["description"]}</p>'
                f'<p style="margin:0; color:#E8163C; font-size:11px;">{badge}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            preview_path = PROJECT_ROOT / "assets" / "templates" / f"preset_{pid}.png"
            if preview_path.exists():
                st.image(str(preview_path), use_container_width=True)

            if st.button(
                "✅ Attivo" if is_selected else "Usa",
                key=f"preset_{pid}",
                use_container_width=True,
                disabled=is_selected,
            ):
                # Apply preset settings
                new_settings = dict(preset["settings"])
                new_settings["preset"] = pid
                # Keep position from existing
                new_settings["position"] = settings["editor"]["subtitle"].get("position", "center")
                new_settings["max_chars_per_line"] = settings["editor"]["subtitle"].get("max_chars_per_line", 25)
                settings["editor"]["subtitle"] = new_settings
                # Caption mode (HeyGen built-in) is OFF when using custom presets
                settings["heygen"]["subtitle_source"] = "custom"
                settings["heygen"]["caption"] = False
                save_settings(settings)
                st.rerun()

    st.divider()

    # ── ALTERNATIVE: HeyGen built-in ──
    with st.expander("⚙️ Oppure usa i sottotitoli integrati di HeyGen"):
        col1, col2 = st.columns([2, 1])
        with col1:
            hp = PROJECT_ROOT / "assets" / "templates" / "heygen_caption_preview.png"
            if hp.exists():
                st.image(str(hp), width=240)
            st.caption("Sottotitoli generati direttamente da HeyGen, stile classico bianco in basso")
        with col2:
            using_heygen = settings["heygen"].get("subtitle_source") == "heygen"
            if using_heygen:
                st.success("✅ HeyGen attivo")
                if st.button("Torna ai preset Custom", use_container_width=True):
                    settings["heygen"]["subtitle_source"] = "custom"
                    settings["heygen"]["caption"] = False
                    save_settings(settings)
                    st.rerun()
            else:
                if st.button("Usa HeyGen", use_container_width=True):
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
    st.markdown(f'<h1 translate="no" lang="it">{STEP_TITLES[6]}</h1>', unsafe_allow_html=True)
    st.caption("Caption, hashtag e impostazioni di pubblicazione")

    settings["publisher"]["caption_template"] = st.text_area(
        "Template Caption (usa {summary_bullets} per le notizie)",
        settings["publisher"]["caption_template"], height=200,
    )

    st.divider()
    st.subheader("Account")
    ig_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if ig_id:
        st.success(f"Instagram collegato — ID: {ig_id}")
    else:
        st.error("INSTAGRAM_BUSINESS_ACCOUNT_ID mancante in .env")

    if st.button("💾 Salva", type="secondary"):
        save_settings(settings)
        st.success("Salvato")

    st.divider()
    nav_buttons(6, bool(ig_id))


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
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📱 Pubblica su Instagram", type="primary", use_container_width=True):
                with st.spinner("Pubblicazione in corso..."):
                    try:
                        from src.config_loader import load_config
                        from src.publisher import publish_to_instagram
                        from src.scraper import load_articles
                        from src.auth import check_and_refresh_token

                        cfg = load_config(check_ffmpeg=False)
                        articles = load_articles(run_dir)
                        token = check_and_refresh_token(
                            cfg.meta_access_token, cfg.meta_app_id, cfg.meta_app_secret
                        )
                        media_id = publish_to_instagram(
                            final_path, articles, cfg.publisher,
                            cfg.instagram_business_account_id, token,
                        )
                        st.success(f"✅ Pubblicato! Media ID: {media_id}")
                    except Exception as e:
                        st.error(f"Errore: {e}")
        with col2:
            st.caption("La pubblicazione carica il video sul tuo account Instagram Business")

    nav_buttons(7, True, next_label="Fine")
