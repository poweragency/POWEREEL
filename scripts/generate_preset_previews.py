"""Generate preview images for each subtitle preset."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
import numpy as np

from src.editor import _render_subtitle_nicktrading
from src.subtitle_presets import PRESETS

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "templates"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_preview(preset_id: str, settings: dict) -> Path:
    sample_text = "Bitcoin esplode oltre" if preset_id != "minimal" else "bitcoin esplode oltre"
    emoji = "🚀" if settings.get("add_emoji") else ""

    img_array = _render_subtitle_nicktrading(
        text=sample_text,
        highlight_idx=0,
        font_path=settings["font_path"],
        font_size=settings["font_size"],
        font_color=settings["font_color"],
        accent_color=settings["accent_color"],
        stroke_color=settings["stroke_color"],
        stroke_width=settings["stroke_width"],
        highlight_style=settings.get("highlight_style", "box"),
        uppercase=settings.get("uppercase", True),
        emoji=emoji,
        max_line_width=900,
    )

    # Build a fake video frame: dark gradient background
    sub_img = Image.fromarray(img_array)
    sw, sh = sub_img.size

    bg_w, bg_h = 720, 480
    bg = Image.new("RGB", (bg_w, bg_h))
    # Vertical gradient
    for y in range(bg_h):
        v = int(20 + 40 * (y / bg_h))
        for x in range(bg_w):
            bg.putpixel((x, y), (v, v, v + 5))

    # Paste subtitle image centered
    scale = min(0.85 * bg_w / sw, 0.7 * bg_h / sh)
    new_w = int(sw * scale)
    new_h = int(sh * scale)
    sub_resized = sub_img.resize((new_w, new_h), Image.LANCZOS)

    paste_x = (bg_w - new_w) // 2
    paste_y = bg_h - new_h - 30
    bg.paste(sub_resized, (paste_x, paste_y), sub_resized)

    out_path = OUTPUT_DIR / f"preset_{preset_id}.png"
    bg.save(out_path)
    print(f"Generated: {out_path}")
    return out_path


for preset_id, preset in PRESETS.items():
    make_preview(preset_id, preset["settings"])

print("Done!")
