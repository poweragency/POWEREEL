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
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return {"groups": [], "looks": {}, "voices": []}
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/avatar_group.list",
            headers={"X-Api-Key": api_key}, timeout=15,
        )
        groups = r.json().get("data", {}).get("avatar_group_list", [])

        looks = {}
        for g in groups:
            r2 = httpx.get(
                f"https://api.heygen.com/v2/avatar_group/{g['id']}/avatars",
                headers={"X-Api-Key": api_key}, timeout=15,
            )
            if r2.status_code == 200:
                avatar_list = r2.json().get("data", {}).get("avatar_list", [])
                looks[g["name"]] = [
                    {
                        "look_id": a.get("id", a.get("avatar_id", "")),
                        "name": a.get("name", "Default"),
                        "image_url": a.get("image_url", ""),
                    }
                    for a in avatar_list if a.get("id") or a.get("avatar_id")
                ]

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


def run_pipeline_background(dry_run: bool):
    """Launch pipeline in a background thread."""
    def _run():
        try:
            cmd = [
                sys.executable, "-c",
                f"from src.pipeline import run_pipeline; "
                f"run_pipeline(dry_run={dry_run})"
            ]
            log_path = PROJECT_ROOT / "logs" / "wizard_run.log"
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as logf:
                proc = subprocess.run(
                    cmd, stdout=logf, stderr=subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT), timeout=900,
                )
                st.session_state.gen_returncode = proc.returncode
        except Exception as e:
            st.session_state.gen_error = str(e)
        finally:
            st.session_state.gen_running = False

    st.session_state.gen_running = True
    st.session_state.gen_started_at = time.time()
    threading.Thread(target=_run, daemon=True).start()


# ── State ────────────────────────────────────────────────────────────────────

settings = load_settings()
data = get_heygen_data()

if "step" not in st.session_state:
    st.session_state.step = 1

if "gen_running" not in st.session_state:
    st.session_state.gen_running = False

STEPS = [
    "1. Avatar & Look",
    "2. Voce",
    "3. Fonti Notizie",
    "4. Script & Tono",
    "5. Stile Sottotitoli",
    "6. Instagram",
    "7. Genera & Pubblica",
]


# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("⚡ POWEREEL")
st.sidebar.caption("Wizard step-by-step")

credits = get_heygen_credits()
if credits >= 0:
    st.sidebar.metric("Crediti HeyGen API", credits)

st.sidebar.divider()
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
    st.session_state.step = 1
    st.rerun()


# ── Wizard navigation ───────────────────────────────────────────────────────

def nav_buttons(current_step: int, can_proceed: bool, next_label: str = "Avanti →"):
    col_back, col_space, col_next = st.columns([1, 3, 1])
    with col_back:
        if current_step > 1:
            if st.button("← Indietro", use_container_width=True):
                st.session_state.step -= 1
                st.rerun()
    with col_next:
        if current_step < len(STEPS):
            if st.button(next_label, type="primary", use_container_width=True, disabled=not can_proceed):
                st.session_state.step += 1
                st.rerun()


# ── STEP 1: Avatar & Look ────────────────────────────────────────────────────

if st.session_state.step == 1:
    st.title("Step 1 — Avatar & Look")
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
    st.title("Step 2 — Voce")
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
    st.title("Step 3 — Fonti Notizie")
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
    st.title("Step 4 — Script & Tono")
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
    st.title("Step 5 — Stile Sottotitoli")

    current_source = settings["heygen"].get("subtitle_source", "custom")

    col_h, col_c = st.columns(2)
    with col_h:
        is_heygen = current_source == "heygen"
        border_h = "3px solid #E8163C" if is_heygen else "1px solid #444"
        st.markdown(
            f'<div style="border:{border_h}; border-radius:12px; padding:10px; text-align:center;">'
            f'<h4>HeyGen integrati</h4>'
            f'<p style="font-size:13px; color:#aaa;">Sottotitoli classici di HeyGen, bianchi in basso</p></div>',
            unsafe_allow_html=True,
        )
        hp = PROJECT_ROOT / "assets" / "templates" / "heygen_caption_preview.png"
        if hp.exists():
            st.image(str(hp), use_container_width=True)
        if st.button("✅ Attivo" if is_heygen else "Usa HeyGen", key="src_h",
                     use_container_width=True, disabled=is_heygen):
            settings["heygen"]["subtitle_source"] = "heygen"
            settings["heygen"]["caption"] = True
            save_settings(settings)
            st.rerun()

    with col_c:
        is_custom = current_source == "custom"
        border_c = "3px solid #E8163C" if is_custom else "1px solid #444"
        st.markdown(
            f'<div style="border:{border_c}; border-radius:12px; padding:10px; text-align:center;">'
            f'<h4>Custom (nicktrading_)</h4>'
            f'<p style="font-size:13px; color:#aaa;">Box rosso sulla parola chiave, sync Whisper</p></div>',
            unsafe_allow_html=True,
        )
        cp = PROJECT_ROOT / "assets" / "templates" / "custom_caption_preview.png"
        if cp.exists():
            st.image(str(cp), use_container_width=True)
        if st.button("✅ Attivo" if is_custom else "Usa Custom", key="src_c",
                     use_container_width=True, disabled=is_custom):
            settings["heygen"]["subtitle_source"] = "custom"
            settings["heygen"]["caption"] = False
            save_settings(settings)
            st.rerun()

    if current_source == "custom":
        st.divider()
        st.subheader("Personalizza Custom")
        sub = settings["editor"]["subtitle"]
        c1, c2 = st.columns(2)
        with c1:
            sub["font_size"] = st.slider("Dimensione font", 30, 120, sub["font_size"])
            sub["words_per_subtitle"] = st.slider("Parole per frame", 2, 6, sub["words_per_subtitle"])
        with c2:
            sub["font_color"] = st.color_picker("Colore testo", sub["font_color"])
            sub["accent_color"] = st.color_picker("Colore box", sub["accent_color"])
        settings["editor"]["subtitle"] = sub
        if st.button("💾 Salva stile", type="secondary"):
            save_settings(settings)
            st.success("Salvato")

    st.divider()
    nav_buttons(5, True)


# ── STEP 6: Instagram ────────────────────────────────────────────────────────

elif st.session_state.step == 6:
    st.title("Step 6 — Instagram")
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
    st.title("Step 7 — Genera & Pubblica")
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
    if st.session_state.gen_running:
        elapsed = int(time.time() - st.session_state.get("gen_started_at", time.time()))
        st.info(f"⏳ Generazione in corso... ({elapsed}s) — può impiegare 5-8 minuti")
        st.progress(min(elapsed / 480, 0.95))

        # Show log tail
        log_path = PROJECT_ROOT / "logs" / "wizard_run.log"
        if log_path.exists():
            with st.expander("📜 Log live"):
                lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                st.code("\n".join(lines[-15:]))

        # Auto-refresh every 5 sec
        time.sleep(5)
        st.rerun()
    else:
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
    if final_path.exists() and not st.session_state.gen_running:
        st.divider()
        st.subheader("🎬 Anteprima")

        if script_path.exists():
            with st.expander("📝 Script"):
                st.text(script_path.read_text(encoding="utf-8"))

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
