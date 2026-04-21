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
    initial_sidebar_state="expanded",
)

# Disable browser auto-translation everywhere
st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>html, body { translate: no !important; }</style>
    <script>
        document.documentElement.setAttribute('translate', 'no');
        document.documentElement.setAttribute('lang', 'it');
        document.body.setAttribute('translate', 'no');
    </script>
    """,
    unsafe_allow_html=True,
)

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


# ── Authentication ───────────────────────────────────────────────────────────

def check_password() -> bool:
    app_password = os.getenv("APP_PASSWORD", "")
    if not app_password:
        return True
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    st.title("⚡ POWEREEL")
    st.markdown("### Accesso riservato")
    password = st.text_input("Password", type="password")
    if st.button("Accedi", type="primary"):
        if password == app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Password errata")
    return False


if not check_password():
    st.stop()


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
    """Check if a generation is currently running (file-based)."""
    return RUN_MARKER.exists()


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
    final_path = PROJECT_ROOT / "output" / today / "final.mp4"
    script_path = PROJECT_ROOT / "output" / today / "script.txt"

    # Recap
    with st.expander("📋 Riepilogo configurazione", expanded=False):
        st.write(f"**Avatar/Look:** `{settings['heygen']['avatar_id'][:16]}...`")
        st.write(f"**Voce:** `{settings['heygen']['voice_id'][:16]}...`")
        st.write(f"**Feed:** {len(settings['scraper']['feeds'])} attivi")
        st.write(f"**Durata:** {settings['scriptwriter']['target_duration_seconds']}s")
        st.write(f"**Sottotitoli:** {settings['heygen'].get('subtitle_source', 'custom')}")

    st.divider()

    # Generation
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

    # Show last result
    if final_path.exists() and not running:
        st.divider()
        st.subheader("🎬 Anteprima")

        if script_path.exists():
            with st.expander("📝 Script"):
                st.text(script_path.read_text(encoding="utf-8"))

        # Reel-sized preview (~360px wide, 9:16 ratio)
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
                        articles = load_articles(PROJECT_ROOT / "output" / today)
                        token = check_and_refresh_token(
                            cfg.meta_access_token, cfg.meta_app_id, cfg.meta_app_secret
                        )
                        media_id = publish_to_instagram(
                            final_path, articles, cfg.publisher,
                            cfg.instagram_business_account_id, token,
                        )
                        st.success(f"✅ Pubblicato! Media ID: {media_id}")
                    except Exception as e:
                        st.error(f"Errore pubblicazione: {e}")
        with col2:
            st.caption("La pubblicazione carica il video sul tuo account Instagram Business")

    nav_buttons(7, True, next_label="Fine")
