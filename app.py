"""POWEREEL — Control Panel (Streamlit Dashboard)."""

import json
import os
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

# Load env — support both local .env and Streamlit Cloud secrets
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
elif (PROJECT_ROOT / ".env").exists():
    load_dotenv(PROJECT_ROOT / ".env")

# Streamlit Cloud: load secrets into environment variables
if hasattr(st, "secrets"):
    for key in ["HEYGEN_API_KEY", "ANTHROPIC_API_KEY", "META_ACCESS_TOKEN",
                 "META_APP_ID", "META_APP_SECRET", "INSTAGRAM_BUSINESS_ACCOUNT_ID",
                 "APP_PASSWORD"]:
        if key in st.secrets:
            os.environ[key] = st.secrets[key]

# ── Authentication ───────────────────────────────────────────────────────────

def check_password() -> bool:
    """Block access unless the correct password is entered."""
    app_password = os.getenv("APP_PASSWORD", "")

    # No password set = no protection (local dev)
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
            st.error("❌ Password errata")
    return False

if not check_password():
    st.stop()


# ── Helpers ──────────────────────────────────────────────────────────────────


def load_settings() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_settings(settings: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_heygen_avatars(include_stock: bool = False) -> list[dict]:
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/avatars",
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        data = r.json().get("data", {}).get("avatars", [])
        seen = set()
        result = []
        for a in data:
            aid = a["avatar_id"]
            if aid in seen:
                continue
            seen.add(aid)
            # Custom avatars have type=None, stock have type set
            is_custom = a.get("type") is None
            if is_custom or include_stock:
                a["is_custom"] = is_custom
                result.append(a)
        return result
    except Exception:
        return []


def get_heygen_avatar_groups() -> list[dict]:
    """Get avatar groups with looks info."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/avatar_group.list",
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        return r.json().get("data", {}).get("avatar_group_list", [])
    except Exception:
        return []


def get_heygen_voices() -> list[dict]:
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/voices",
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        voices = r.json().get("data", {}).get("voices", [])
        return [v for v in voices if v.get("type") == "custom"]
    except Exception:
        return []


def get_heygen_credits() -> int:
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return -1
    try:
        r = httpx.get(
            "https://api.heygen.com/v2/user/remaining_quota",
            headers={"X-Api-Key": api_key},
            timeout=10,
        )
        return r.json().get("data", {}).get("remaining_quota", 0)
    except Exception:
        return -1


def get_past_runs() -> list[dict]:
    output_dir = PROJECT_ROOT / "output"
    runs = []
    if not output_dir.exists():
        return runs
    for folder in sorted(output_dir.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        try:
            date.fromisoformat(folder.name)
        except ValueError:
            continue
        meta_path = folder / "metadata.json"
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        runs.append({
            "date": folder.name,
            "path": folder,
            "has_final": (folder / "final.mp4").exists(),
            "has_script": (folder / "script.txt").exists(),
            "status": meta.get("status", "unknown"),
            "dry_run": meta.get("dry_run", True),
            "publish_id": meta.get("publish_id"),
        })
    return runs


# ── Sidebar ──────────────────────────────────────────────────────────────────

settings = load_settings()

st.sidebar.title("⚡ POWEREEL")
st.sidebar.caption("Pannello di Controllo")

# Credits display
credits = get_heygen_credits()
if credits >= 0:
    st.sidebar.metric("Crediti HeyGen API", credits)

st.sidebar.divider()

page = st.sidebar.radio(
    "Sezione",
    ["🎭 Avatar & Voce", "📰 Fonti Notizie", "✍️ Script & Tono", "🎨 Stile Sottotitoli", "📱 Instagram"],
)

# ── Pages ────────────────────────────────────────────────────────────────────

if page == "🎭 Avatar & Voce":
    st.title("🎭 Avatar & Voce")

    # ── My Avatars ──
    st.subheader("I Miei Avatar")
    show_stock = st.toggle("Mostra anche avatar stock HeyGen", False)
    avatars = get_heygen_avatars(include_stock=show_stock)
    groups = get_heygen_avatar_groups()

    if avatars:
        current_avatar = settings["heygen"]["avatar_id"]

        # Separate custom and stock
        custom_avatars = [a for a in avatars if a.get("is_custom")]
        stock_avatars = [a for a in avatars if not a.get("is_custom")]

        # Show custom avatars
        if custom_avatars:
            cols = st.columns(min(len(custom_avatars), 3))
            for i, avatar in enumerate(custom_avatars):
                with cols[i % len(cols)]:
                    is_selected = avatar["avatar_id"] == current_avatar
                    border = "3px solid #E8163C" if is_selected else "1px solid #444"

                    # Find looks count for this avatar
                    looks = 0
                    for g in groups:
                        if g["name"] == avatar["avatar_name"]:
                            looks = g.get("num_looks", 0)
                            break

                    st.markdown(
                        f'<div style="border:{border}; border-radius:12px; padding:10px; text-align:center; background:#1a1a2e;">'
                        f'<img src="{avatar["preview_image_url"]}" style="width:100%; border-radius:8px; aspect-ratio:9/16; object-fit:cover;">'
                        f'<h4 style="margin:8px 0 2px;">{avatar["avatar_name"]}</h4>'
                        f'<p style="margin:0; color:#888; font-size:12px;">{looks} look{"s" if looks != 1 else ""} disponibil{"i" if looks != 1 else "e"}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Preview video
                    if avatar.get("preview_video_url"):
                        with st.expander("🎥 Preview video"):
                            st.video(avatar["preview_video_url"])

                    if st.button(
                        "✅ Selezionato" if is_selected else "Seleziona",
                        key=f"avatar_{avatar['avatar_id']}",
                        use_container_width=True,
                        disabled=is_selected,
                        type="primary" if is_selected else "secondary",
                    ):
                        settings["heygen"]["avatar_id"] = avatar["avatar_id"]
                        save_settings(settings)
                        st.rerun()

        # Show stock avatars if enabled
        if stock_avatars and show_stock:
            st.divider()
            st.subheader("Avatar Stock HeyGen")
            st.caption("Avatar professionali pronti all'uso")
            cols = st.columns(4)
            for i, avatar in enumerate(stock_avatars[:12]):  # Show max 12
                with cols[i % 4]:
                    is_selected = avatar["avatar_id"] == current_avatar
                    border = "3px solid #E8163C" if is_selected else "1px solid #333"
                    st.markdown(
                        f'<div style="border:{border}; border-radius:10px; padding:6px; text-align:center;">'
                        f'<img src="{avatar["preview_image_url"]}" style="width:100%; border-radius:6px;">'
                        f'<p style="margin:4px 0; font-size:12px;">{avatar["avatar_name"]}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✅" if is_selected else "Usa",
                        key=f"avatar_stock_{avatar['avatar_id']}",
                        use_container_width=True,
                        disabled=is_selected,
                    ):
                        settings["heygen"]["avatar_id"] = avatar["avatar_id"]
                        save_settings(settings)
                        st.rerun()

    else:
        st.warning("Impossibile caricare gli avatar. Verifica la API key di HeyGen.")

    st.divider()

    # ── Voices ──
    st.subheader("Seleziona Voce")
    voices = get_heygen_voices()

    if voices:
        current_voice = settings["heygen"]["voice_id"]
        for voice in voices:
            is_selected = voice["voice_id"] == current_voice
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                icon = "✅" if is_selected else "🎙️"
                st.write(f"{icon} **{voice['name']}** ({voice['language']})")
            with col2:
                if voice.get("preview_audio"):
                    st.audio(voice["preview_audio"])
            with col3:
                if not is_selected:
                    if st.button("Seleziona", key=f"voice_{voice['voice_id']}"):
                        settings["heygen"]["voice_id"] = voice["voice_id"]
                        save_settings(settings)
                        st.rerun()
                else:
                    st.write("✅ Attiva")

    else:
        st.warning("Nessuna voce custom trovata.")

    st.divider()

    # ── Video settings ──
    st.subheader("Impostazioni Video")
    col1, col2 = st.columns(2)
    with col1:
        settings["heygen"]["video_width"] = st.number_input("Larghezza", value=settings["heygen"]["video_width"], key="vw")
    with col2:
        settings["heygen"]["video_height"] = st.number_input("Altezza", value=settings["heygen"]["video_height"], key="vh")

    st.caption("Default: 1080x1920 (9:16 verticale per Reels)")

    if st.button("💾 Salva", type="primary", key="save_avatar"):
        save_settings(settings)
        st.success("✅ Salvato!")
    else:
        st.warning("Nessuna voce custom trovata.")


elif page == "📰 Fonti Notizie":
    st.title("📰 Fonti Notizie")
    st.markdown("Gestisci i feed RSS da cui vengono prese le notizie.")

    feeds = settings["scraper"]["feeds"]

    for i, feed in enumerate(feeds):
        col1, col2, col3, col4 = st.columns([3, 5, 1, 1])
        with col1:
            feeds[i]["name"] = st.text_input("Nome", feed["name"], key=f"feed_name_{i}")
        with col2:
            feeds[i]["url"] = st.text_input("URL Feed RSS", feed["url"], key=f"feed_url_{i}")
        with col3:
            feeds[i]["lang"] = st.selectbox("Lingua", ["it", "en"], index=0 if feed["lang"] == "it" else 1, key=f"feed_lang_{i}")
        with col4:
            st.write("")
            st.write("")
            if st.button("🗑️", key=f"del_feed_{i}"):
                feeds.pop(i)
                settings["scraper"]["feeds"] = feeds
                save_settings(settings)
                st.rerun()

    st.divider()

    # Add new feed
    st.subheader("Aggiungi Feed")
    col1, col2, col3 = st.columns([3, 5, 2])
    with col1:
        new_name = st.text_input("Nome", "", key="new_feed_name")
    with col2:
        new_url = st.text_input("URL RSS", "", key="new_feed_url")
    with col3:
        new_lang = st.selectbox("Lingua", ["it", "en"], key="new_feed_lang")

    if st.button("➕ Aggiungi Feed"):
        if new_name and new_url:
            feeds.append({"name": new_name, "url": new_url, "lang": new_lang})
            settings["scraper"]["feeds"] = feeds
            save_settings(settings)
            st.success(f"Feed '{new_name}' aggiunto!")
            st.rerun()

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        settings["scraper"]["max_articles_per_feed"] = st.number_input(
            "Max articoli per feed", 1, 20, settings["scraper"]["max_articles_per_feed"]
        )
    with col2:
        settings["scraper"]["max_total_articles"] = st.number_input(
            "Max articoli totali", 1, 50, settings["scraper"]["max_total_articles"]
        )

    if st.button("💾 Salva Impostazioni", type="primary"):
        save_settings(settings)
        st.success("✅ Salvato!")


elif page == "✍️ Script & Tono":
    st.title("✍️ Script & Tono")

    col1, col2 = st.columns(2)
    with col1:
        settings["scriptwriter"]["target_duration_seconds"] = st.slider(
            "Durata video (secondi)", 15, 90, settings["scriptwriter"]["target_duration_seconds"]
        )
    with col2:
        settings["scriptwriter"]["tone"] = st.text_input(
            "Tono", settings["scriptwriter"]["tone"]
        )

    settings["scriptwriter"]["system_prompt"] = st.text_area(
        "System Prompt (istruzioni per Claude)",
        settings["scriptwriter"]["system_prompt"],
        height=300,
    )

    st.caption("Variabili disponibili: `{duration}`, `{tone}`, `{word_count}`")

    if st.button("💾 Salva", type="primary"):
        save_settings(settings)
        st.success("✅ Salvato!")


elif page == "🎨 Stile Sottotitoli":
    st.title("🎨 Stile Sottotitoli")

    sub = settings["editor"]["subtitle"]

    col1, col2 = st.columns(2)
    with col1:
        sub["font_size"] = st.slider("Dimensione font", 30, 120, sub["font_size"])
        sub["words_per_subtitle"] = st.slider("Parole per frame", 2, 6, sub["words_per_subtitle"])
        sub["stroke_width"] = st.slider("Spessore bordo", 1, 10, sub["stroke_width"])
    with col2:
        sub["font_color"] = st.color_picker("Colore testo", sub["font_color"])
        sub["accent_color"] = st.color_picker("Colore box highlight", sub["accent_color"])
        sub["stroke_color"] = st.color_picker("Colore bordo", sub["stroke_color"])

    sub["uppercase"] = st.toggle("TUTTO MAIUSCOLO", sub.get("uppercase", True))

    font_options = {
        "Bebas Neue": "./assets/fonts/BebasNeue-Regular.ttf",
        "Montserrat Bold": "./assets/fonts/Montserrat-Bold.ttf",
    }
    current_font = "Bebas Neue" if "Bebas" in sub["font_path"] else "Montserrat Bold"
    selected_font = st.selectbox("Font", list(font_options.keys()), index=list(font_options.keys()).index(current_font))
    sub["font_path"] = font_options[selected_font]

    settings["editor"]["subtitle"] = sub

    st.divider()

    # Music
    st.subheader("🎵 Musica di Background")
    music_path = Path(settings["editor"]["background_music"]["path"])
    if music_path.exists():
        st.audio(str(music_path))
        settings["editor"]["background_music"]["volume"] = st.slider(
            "Volume musica", 0.0, 0.3, settings["editor"]["background_music"]["volume"], 0.01
        )
    else:
        st.info("Nessuna musica. Carica un file MP3 in `assets/music/default_bg.mp3`")

    uploaded_music = st.file_uploader("Carica musica di background", type=["mp3"])
    if uploaded_music:
        music_dest = PROJECT_ROOT / "assets" / "music" / "default_bg.mp3"
        music_dest.write_bytes(uploaded_music.read())
        st.success("✅ Musica caricata!")
        st.rerun()

    if st.button("💾 Salva", type="primary"):
        save_settings(settings)
        st.success("✅ Salvato!")


elif page == "📱 Instagram":
    st.title("📱 Instagram")

    st.subheader("Impostazioni Pubblicazione")

    settings["pipeline"]["dry_run"] = st.toggle(
        "Modalità Dry Run (non pubblica)", settings["pipeline"]["dry_run"]
    )

    # Schedule
    cron = settings["pipeline"]["schedule_cron"]
    st.subheader("⏰ Programmazione")

    schedule_options = {
        "Ogni giorno alle 8:00": "0 8 * * *",
        "Ogni giorno alle 12:00": "0 12 * * *",
        "Ogni giorno alle 18:00": "0 18 * * *",
        "Ogni giorno alle 9:00": "0 9 * * *",
        "Custom": cron,
    }

    # Find current
    current_schedule = "Custom"
    for label, val in schedule_options.items():
        if val == cron:
            current_schedule = label
            break

    selected_schedule = st.selectbox("Orario pubblicazione", list(schedule_options.keys()),
                                     index=list(schedule_options.keys()).index(current_schedule))

    if selected_schedule == "Custom":
        settings["pipeline"]["schedule_cron"] = st.text_input("Cron expression", cron)
    else:
        settings["pipeline"]["schedule_cron"] = schedule_options[selected_schedule]

    st.divider()

    # Caption template
    st.subheader("📝 Template Caption")
    settings["publisher"]["caption_template"] = st.text_area(
        "Caption (usa {summary_bullets} per le notizie)",
        settings["publisher"]["caption_template"],
        height=150,
    )

    st.divider()

    # Account info
    st.subheader("🔑 Account Collegato")
    ig_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if ig_id:
        st.success(f"Account Instagram collegato (ID: {ig_id})")
    else:
        st.warning("Nessun account Instagram configurato")

    if st.button("💾 Salva", type="primary"):
        save_settings(settings)
        st.success("✅ Salvato!")


