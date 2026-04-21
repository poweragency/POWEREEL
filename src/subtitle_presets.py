"""Subtitle style presets — ready-to-use looks for the editor."""

from __future__ import annotations

# Emoji map for crypto/finance keywords
EMOJI_MAP = {
    "bitcoin": "₿",
    "btc": "₿",
    "crypto": "🪙",
    "criptovalut": "🪙",
    "ethereum": "Ξ",
    "eth": "Ξ",
    "crollo": "📉",
    "crollat": "📉",
    "scendi": "📉",
    "perdita": "📉",
    "salita": "📈",
    "boom": "🚀",
    "esplos": "💥",
    "record": "🏆",
    "truffa": "⚠️",
    "frega": "⚠️",
    "rubat": "🚨",
    "milioni": "💰",
    "miliardi": "💸",
    "dollari": "💵",
    "euro": "💶",
    "guadagn": "💰",
    "perdere": "📉",
    "attenzione": "⚠️",
    "stop": "🛑",
    "guerra": "⚔️",
    "trump": "🇺🇸",
    "elon": "🚀",
    "musk": "🚀",
    "fed": "🏦",
    "banca": "🏦",
    "mercato": "📊",
    "borsa": "📊",
    "nucleare": "☢️",
    "iran": "🇮🇷",
    "blackrock": "🖤",
    "etf": "📈",
    "wall": "🏛️",
    "trading": "📊",
    "investiment": "💼",
    "incredibile": "🤯",
    "pazzesco": "🤯",
    "important": "❗",
    "urgent": "🚨",
}


def find_emoji(text: str) -> str:
    """Find best matching emoji for a phrase."""
    text_lower = text.lower()
    for keyword, emoji in EMOJI_MAP.items():
        if keyword in text_lower:
            return emoji
    return ""


# ── Preset definitions ──────────────────────────────────────────────────────

PRESETS = {
    "classic": {
        "name": "Classic (nicktrading_)",
        "description": "Box rosso sulla parola chiave, font Bebas Neue grande",
        "settings": {
            "font_path": "./assets/fonts/BebasNeue-Regular.ttf",
            "font_size": 90,
            "font_color": "#FFFFFF",
            "accent_color": "#E8163C",
            "stroke_color": "#000000",
            "stroke_width": 5,
            "words_per_subtitle": 3,
            "uppercase": True,
            "add_emoji": False,
            "highlight_style": "box",  # "box" or "color"
        },
    },
    "with_emoji": {
        "name": "Con Emoji",
        "description": "Stile Classic + emoji contestuale sopra ogni frase",
        "settings": {
            "font_path": "./assets/fonts/BebasNeue-Regular.ttf",
            "font_size": 90,
            "font_color": "#FFFFFF",
            "accent_color": "#E8163C",
            "stroke_color": "#000000",
            "stroke_width": 5,
            "words_per_subtitle": 3,
            "uppercase": True,
            "add_emoji": True,
            "highlight_style": "box",
        },
    },
    "hormozi_yellow": {
        "name": "Hormozi (giallo)",
        "description": "Testo giallo, bordo nero spesso, parola chiave gialla evidenziata",
        "settings": {
            "font_path": "./assets/fonts/Montserrat-Bold.ttf",
            "font_size": 80,
            "font_color": "#FFFFFF",
            "accent_color": "#FFD700",
            "stroke_color": "#000000",
            "stroke_width": 6,
            "words_per_subtitle": 2,
            "uppercase": True,
            "add_emoji": False,
            "highlight_style": "color",  # change color instead of box
        },
    },
    "minimal": {
        "name": "Minimal Clean",
        "description": "Sottotitoli puliti piccoli in basso, no box, no maiuscolo",
        "settings": {
            "font_path": "./assets/fonts/Montserrat-Bold.ttf",
            "font_size": 50,
            "font_color": "#FFFFFF",
            "accent_color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 3,
            "words_per_subtitle": 4,
            "uppercase": False,
            "add_emoji": False,
            "highlight_style": "none",  # no highlight
        },
    },
}
