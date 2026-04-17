"""POWEREEL — Control Panel (Streamlit Dashboard)."""

import os
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


@st.cache_data(ttl=300)
def get_heygen_data() -> dict:
    """Get all avatar groups and their looks in one cached call."""
    api_key = os.getenv("HEYGEN_API_KEY", "")
    if not api_key:
        return {"groups": [], "looks": {}}
    try:
        # Get avatar groups (user's own avatars)
        r = httpx.get(
            "https://api.heygen.com/v2/avatar_group.list",
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        groups = r.json().get("data", {}).get("avatar_group_list", [])

        # Get looks for each group
        looks = {}
        for g in groups:
            gid = g["id"]
            r2 = httpx.get(
                f"https://api.heygen.com/v2/avatar_group/{gid}/avatars",
                headers={"X-Api-Key": api_key},
                timeout=15,
            )
            if r2.status_code == 200:
                avatar_list = r2.json().get("data", {}).get("avatar_list", [])
                looks[g["name"]] = [
                    {
                        "look_id": a.get("id", a.get("avatar_id", "")),
                        "name": a.get("name", "Default"),
                        "image_url": a.get("image_url", ""),
                    }
                    for a in avatar_list
                    if a.get("id") or a.get("avatar_id")
                ]

        return {"groups": groups, "looks": looks}
    except Exception:
        return {"groups": [], "looks": {}}


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=120)
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

    heygen_data = get_heygen_data()
    groups = heygen_data["groups"]
    all_looks = heygen_data["looks"]
    current_avatar = settings["heygen"]["avatar_id"]

    # ── Step 1: Scegli Avatar ──
    st.subheader("1. Scegli Avatar")

    if groups:
        avatar_names = [g["name"] for g in groups]

        # Find which avatar is currently selected
        current_group = avatar_names[0]
        for gname, looks in all_looks.items():
            for look in looks:
                if look["look_id"] == current_avatar:
                    current_group = gname
                    break

        selected_group = st.radio(
            "I tuoi avatar",
            avatar_names,
            index=avatar_names.index(current_group) if current_group in avatar_names else 0,
            horizontal=True,
        )

        # ── Step 2: Scegli Look ──
        st.subheader("2. Scegli Look")
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
        else:
            st.info("Nessun look trovato per questo avatar.")
    else:
        st.warning("Impossibile caricare gli avatar. Verifica la API key di HeyGen.")

    st.divider()

    # ── Voce ──
    st.subheader("3. Scegli Voce")
    voices = get_heygen_voices()
    current_voice = settings["heygen"]["voice_id"]

    if voices:
        for voice in voices:
            is_selected = voice["voice_id"] == current_voice
            col1, col2 = st.columns([4, 1])
            with col1:
                icon = "✅" if is_selected else "🎙️"
                st.write(f"{icon} **{voice['name']}** — {voice['language']}")
            with col2:
                if not is_selected:
                    if st.button("Seleziona", key=f"vc_{voice['voice_id']}", use_container_width=True):
                        settings["heygen"]["voice_id"] = voice["voice_id"]
                        save_settings(settings)
                        st.rerun()
    else:
        st.warning("Nessuna voce custom trovata.")

    st.divider()

    # ── Background ──
    st.subheader("4. Sfondo Video")

    bg_type = st.selectbox(
        "Tipo di sfondo",
        ["color", "image", "video"],
        index=["color", "image", "video"].index(settings["heygen"].get("background_type", "color")),
        format_func=lambda x: {"color": "Colore solido", "image": "Immagine (URL)", "video": "Video (URL)"}[x],
    )
    settings["heygen"]["background_type"] = bg_type

    if bg_type == "color":
        settings["heygen"]["background_value"] = st.color_picker(
            "Colore sfondo", settings["heygen"].get("background_value", "#000000")
        )
    else:
        label = "URL immagine sfondo" if bg_type == "image" else "URL video sfondo"
        settings["heygen"]["background_value"] = st.text_input(
            label, settings["heygen"].get("background_value", "")
        )

    st.caption("Formato: 1080x1920 (9:16 verticale, Reel)")

    if st.button("💾 Salva", type="primary", key="save_avatar"):
        save_settings(settings)
        st.success("✅ Salvato!")


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

    # ── Subtitle source with previews ──
    st.subheader("Scegli Stile Sottotitoli")

    current_source = settings["heygen"].get("subtitle_source", "custom")

    col_h, col_c = st.columns(2)

    with col_h:
        is_heygen = current_source == "heygen"
        border_h = "3px solid #E8163C" if is_heygen else "1px solid #444"
        st.markdown(
            f'<div style="border:{border_h}; border-radius:12px; padding:10px; text-align:center;">'
            f'<h4>HeyGen</h4>'
            f'<p style="font-size:13px; color:#aaa;">Sottotitoli integrati da HeyGen, bianchi in basso, stile pulito</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        heygen_preview = PROJECT_ROOT / "assets" / "templates" / "heygen_caption_preview.png"
        if heygen_preview.exists():
            st.image(str(heygen_preview), use_container_width=True)
        if st.button(
            "✅ Attivo" if is_heygen else "Seleziona",
            key="src_heygen",
            use_container_width=True,
            disabled=is_heygen,
        ):
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
            f'<p style="font-size:13px; color:#aaa;">Box rosso sulla parola chiave, font grande, personalizzabile</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        custom_preview = PROJECT_ROOT / "assets" / "templates" / "custom_caption_preview.png"
        if custom_preview.exists():
            st.image(str(custom_preview), use_container_width=True)
        if st.button(
            "✅ Attivo" if is_custom else "Seleziona",
            key="src_custom",
            use_container_width=True,
            disabled=is_custom,
        ):
            settings["heygen"]["subtitle_source"] = "custom"
            settings["heygen"]["caption"] = False
            save_settings(settings)
            st.rerun()

    st.divider()

    # ── Custom style settings (only if custom) ──
    if current_source == "custom":
        st.subheader("Personalizza Stile Custom")
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
    else:
        st.success("Sottotitoli HeyGen attivi — verranno generati automaticamente nel video.")

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


