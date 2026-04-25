"""Stage 4: Video post-production — nicktrading_ exact style."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

from .config_loader import EditorConfig

# Italian stop words — never highlighted
STOP_WORDS = {
    "il", "la", "lo", "i", "gli", "le", "un", "uno", "una",
    "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
    "del", "dello", "della", "dei", "degli", "delle",
    "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "nel", "nello", "nella", "nei", "negli", "nelle",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "e", "o", "ma", "se", "che", "chi", "cui", "non",
    "è", "sono", "ho", "hai", "ha", "abbiamo", "avete", "hanno",
    "mi", "ti", "si", "ci", "vi", "ne",
    "questo", "questa", "questi", "queste", "quel", "quello", "quella",
    "molto", "poco", "più", "meno", "anche", "ancora", "già", "ora",
    "come", "quando", "dove", "perché", "perchè",
}


# Cached Whisper model — load once, reuse across calls
_WHISPER_MODEL = None


def _get_whisper_model():
    """Lazy-load Whisper model once and cache."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel
        import os
        model_size = os.getenv("WHISPER_MODEL", "tiny")  # "tiny" = ~10x faster than "small"
        logger.info("Caricamento Whisper model '%s' (one-time)...", model_size)
        _WHISPER_MODEL = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            num_workers=2,
        )
    return _WHISPER_MODEL


def _transcribe_with_timestamps(audio_path: Path, language: str = "it") -> list[dict]:
    """Whisper word-level timestamps — fast mode (tiny model + beam_size=1)."""
    import time as _time
    logger.info("Trascrizione audio con Whisper (fast mode)...")
    t0 = _time.time()

    model = _get_whisper_model()
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=False,           # skip VAD = faster
        beam_size=1,                # greedy = faster
        best_of=1,
        condition_on_previous_text=False,
    )

    words = []
    for segment in segments:
        if not segment.words:
            continue
        for word in segment.words:
            words.append({
                "start": word.start,
                "end": word.end,
                "text": word.word.strip(),
            })

    logger.info("Whisper: %d parole trascritte in %.1fs", len(words), _time.time() - t0)
    return words


def _pick_keyword(words: list[str]) -> int:
    """Pick the index of the most impactful word in a chunk.

    Strategy:
    1. Skip stop words
    2. Prefer the longest word
    3. Numbers always win
    """
    best_idx = 0
    best_score = -1

    for i, word in enumerate(words):
        clean = re.sub(r"[^\w]", "", word.lower())
        if not clean:
            continue

        # Numbers get highest priority
        if re.search(r"\d", clean):
            return i

        # Skip stop words
        if clean in STOP_WORDS:
            continue

        # Score by length (longer = more impactful usually)
        score = len(clean)
        if score > best_score:
            best_score = score
            best_idx = i

    return best_idx

logger = logging.getLogger(__name__)


def _split_script_into_chunks(script: str, words_per_chunk: int) -> list[str]:
    words = script.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i : i + words_per_chunk])
        chunks.append(chunk)
    return chunks


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    """Convert #RRGGBB to (r, g, b, a)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _render_subtitle_nicktrading(
    text: str,
    highlight_idx: int,
    font_path: str,
    font_size: int,
    font_color: str = "#FFFFFF",
    accent_color: str = "#E8163C",
    stroke_color: str = "#000000",
    stroke_width: int = 5,
    highlight_style: str = "box",  # "box", "color", or "none"
    uppercase: bool = True,
    emoji: str = "",
    max_line_width: int = 900,
) -> np.ndarray:
    """Render subtitle with configurable style: box highlight, color highlight, or no highlight.
    Optional emoji rendered above the text."""
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    words = (text.upper() if uppercase else text).split()
    if not words:
        return np.zeros((10, 10, 4), dtype=np.uint8)

    if highlight_idx >= len(words):
        highlight_idx = 0

    space_width = font.getlength(" ")
    text_rgba = _hex_to_rgba(font_color)
    accent_rgba = _hex_to_rgba(accent_color)
    stroke_rgba = _hex_to_rgba(stroke_color)

    # Measure each word
    word_data = []
    for w in words:
        bbox = font.getbbox(w)
        w_width = bbox[2] - bbox[0]
        w_height = bbox[3] - bbox[1]
        word_data.append((w, w_width, w_height))

    max_height = max(wh for _, _, wh in word_data)

    # Wrap into lines
    lines = []
    current_line = []
    current_width = 0
    for idx, (word, w_width, w_height) in enumerate(word_data):
        proposed = current_width + (space_width if current_line else 0) + w_width
        if proposed > max_line_width and current_line:
            lines.append(current_line)
            current_line = [(idx, word, w_width, w_height)]
            current_width = w_width
        else:
            current_line.append((idx, word, w_width, w_height))
            current_width = proposed
    if current_line:
        lines.append(current_line)

    box_pad_x = 12
    box_pad_y = 8
    box_radius = 10
    stroke_w = stroke_width
    line_gap = 18

    # Emoji rendered above (use pilmoji + AppleEmojiSource → real iOS-style PNGs)
    emoji_height = 0
    emoji_font = None
    if emoji:
        emoji_size = int(font_size * 1.3)
        emoji_height = emoji_size + 20
        # Pilmoji replaces emoji codepoints with PNG images, so the font is just
        # used for sizing reference — we use the body font for that.
        try:
            emoji_font = ImageFont.truetype(font_path, emoji_size)
        except Exception:
            emoji_font = font

    extra_w = box_pad_x * 2 + stroke_w * 2 + 40
    img_width = int(max_line_width + extra_w)
    img_height = int(
        emoji_height
        + len(lines) * max_height
        + (len(lines) - 1) * line_gap
        + box_pad_y * 2 + stroke_w * 2 + 30
    )

    img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y_text = stroke_w + box_pad_y + 5

    # Render emoji above the text, centered (Apple-style PNGs via pilmoji)
    if emoji and emoji_font is not None:
        try:
            from pilmoji import Pilmoji
            from pilmoji.source import AppleEmojiSource

            with Pilmoji(img, source=AppleEmojiSource) as p:
                # pilmoji.getsize returns (w, h) for the rendered text+emojis
                ew, _eh = p.getsize(emoji, font=emoji_font)
                ex = (img_width - ew) / 2
                p.text((int(ex), int(y_text)), emoji, font=emoji_font, fill=(255, 255, 255, 255))
        except Exception:
            # Fallback to PIL embedded color (Noto/Segoe if available)
            try:
                ebbox = draw.textbbox((0, 0), emoji, font=emoji_font, embedded_color=True)
                ew = ebbox[2] - ebbox[0]
                ex = (img_width - ew) / 2
                draw.text((ex, y_text), emoji, font=emoji_font, embedded_color=True)
            except Exception:
                pass
        y_text += emoji_height

    for line in lines:
        line_text_width = sum(ww for _, _, ww, _ in line) + space_width * (len(line) - 1)
        x = (img_width - line_text_width) / 2

        for idx, word, w_width, w_height in line:
            is_highlighted = (idx == highlight_idx) and highlight_style != "none"

            if is_highlighted and highlight_style == "box":
                # Box behind word
                rx1 = x - box_pad_x
                ry1 = y_text - box_pad_y + 2
                rx2 = x + w_width + box_pad_x
                ry2 = y_text + max_height + box_pad_y - 2
                draw.rounded_rectangle(
                    [rx1, ry1, rx2, ry2],
                    radius=box_radius,
                    fill=accent_rgba,
                )
                draw.text((x, y_text), word, font=font, fill=text_rgba)
            else:
                # Color: highlighted word in accent_color, others in font_color
                fill_color = accent_rgba if is_highlighted else text_rgba
                # Stroke
                for dx in range(-stroke_w, stroke_w + 1):
                    for dy in range(-stroke_w, stroke_w + 1):
                        if dx * dx + dy * dy <= stroke_w * stroke_w:
                            draw.text(
                                (x + dx, y_text + dy), word, font=font,
                                fill=stroke_rgba,
                            )
                draw.text((x, y_text), word, font=font, fill=fill_color)

            x += w_width + space_width

        y_text += max_height + line_gap

    return np.array(img)


def _create_subtitle_clips(
    audio_path: Path,
    video_duration: float,
    video_size: tuple[int, int],
    config: EditorConfig,
) -> list[ImageClip]:
    """Karaoke-style: phrase stays on screen, red highlight moves word-by-word.

    Words are grouped into phrases (~6 words). Each phrase stays displayed
    for its full duration. Within each phrase, a frame is rendered for every
    spoken word with the highlight moving to that word in perfect sync.
    """
    sub_config = config.subtitle
    phrase_size = max(4, sub_config.words_per_subtitle * 2)  # phrase length

    # Get word-level timestamps from audio
    timed_words = _transcribe_with_timestamps(audio_path, language="it")

    if not timed_words:
        logger.warning("Nessuna parola trascritta — sottotitoli saltati")
        return []

    n = len(timed_words)
    clips = []
    total_renders = 0

    # Optional emoji finder
    add_emoji = getattr(sub_config, "add_emoji", False)
    highlight_style = getattr(sub_config, "highlight_style", "box")
    uppercase = getattr(sub_config, "uppercase", True)

    if add_emoji:
        from .subtitle_presets import find_emoji
    else:
        find_emoji = lambda _t: ""

    # Group consecutive words into phrases
    for phrase_start_idx in range(0, n, phrase_size):
        phrase_end_idx = min(n, phrase_start_idx + phrase_size)
        phrase_words = timed_words[phrase_start_idx:phrase_end_idx]
        if not phrase_words:
            continue

        text = " ".join(w["text"] for w in phrase_words)
        phrase_emoji = find_emoji(text) if add_emoji else ""

        # For each word in the phrase, render a clip with that word highlighted
        for local_idx, word in enumerate(phrase_words):
            global_idx = phrase_start_idx + local_idx

            img_array = _render_subtitle_nicktrading(
                text=text,
                highlight_idx=local_idx,
                font_path=sub_config.font_path,
                font_size=sub_config.font_size,
                font_color=sub_config.font_color,
                accent_color=sub_config.accent_color,
                stroke_color=sub_config.stroke_color,
                stroke_width=sub_config.stroke_width,
                highlight_style=highlight_style,
                uppercase=uppercase,
                emoji=phrase_emoji,
            )

            clip = ImageClip(img_array, transparent=True)
            clip = clip.with_start(word["start"])
            # Duration = until next word starts (or end of phrase if last word)
            if global_idx + 1 < n:
                duration = timed_words[global_idx + 1]["start"] - word["start"]
            else:
                duration = max(0.1, word["end"] - word["start"] + 0.2)
            clip = clip.with_duration(max(0.05, duration))
            clip = clip.with_position(("center", 0.58), relative=True)

            clips.append(clip)
            total_renders += 1

    logger.info(
        "Creati %d frame karaoke su %d frasi (testo fermo, rosso che segue voce)",
        total_renders, (n + phrase_size - 1) // phrase_size,
    )
    return clips


def _add_background_music(
    video: VideoFileClip,
    config: EditorConfig,
) -> CompositeAudioClip | None:
    music_path = Path(config.background_music.path)
    if not music_path.exists():
        logger.warning("File musica non trovato: %s (saltato)", music_path)
        return video.audio

    music = AudioFileClip(str(music_path))

    if music.duration < video.duration:
        loops_needed = int(video.duration / music.duration) + 1
        from moviepy import concatenate_audioclips
        music = concatenate_audioclips([music] * loops_needed)

    music = music.subclipped(0, video.duration)
    music = music.with_volume_scaled(config.background_music.volume)

    if video.audio is not None:
        return CompositeAudioClip([video.audio, music])
    return music


def _add_lower_third(
    config: EditorConfig,
    video_duration: float,
) -> ImageClip | None:
    lt = config.lower_third
    if not lt.image:
        return None

    image_path = Path(lt.image)
    if not image_path.exists():
        logger.warning("Lower third non trovato: %s (saltato)", image_path)
        return None

    clip = ImageClip(str(image_path))
    clip = clip.with_duration(min(lt.duration_seconds, video_duration))
    clip = clip.with_position(tuple(lt.position))
    clip = clip.with_start(0)

    logger.info("Lower third aggiunto: %s per %ds", image_path, lt.duration_seconds)
    return clip


def _auto_zoom_vertical(clip: VideoFileClip) -> VideoFileClip:
    """Detect black bars and crop/zoom to fill the full 9:16 frame."""
    frame = clip.get_frame(min(3, clip.duration / 2))
    h, w = frame.shape[:2]

    # Find content boundaries (non-black rows)
    row_brightness = np.mean(frame, axis=(1, 2))
    threshold = 15

    top = 0
    for y in range(h):
        if row_brightness[y] > threshold:
            top = y
            break

    bottom = h - 1
    for y in range(h - 1, 0, -1):
        if row_brightness[y] > threshold:
            bottom = y
            break

    content_height = bottom - top
    content_ratio = content_height / h

    # Only crop if significant black bars (content < 80% of frame)
    if content_ratio >= 0.80:
        logger.info("Video gia' verticale pieno, nessun crop necessario")
        return clip

    logger.info(
        "Black bars rilevate: content y=%d-%d (%.0f%% del frame). Auto-zoom...",
        top, bottom, content_ratio * 100,
    )

    # Crop to content area
    cropped = clip.cropped(y1=top, y2=bottom)

    # Resize to fill the full 9:16 frame (1080x1920)
    target_w, target_h = 1080, 1920
    cropped_w, cropped_h = cropped.size

    # Scale to fill width, then crop height if needed
    scale = target_w / cropped_w
    new_h = int(cropped_h * scale)

    resized = cropped.resized(width=target_w)

    if new_h < target_h:
        # Content is wider than 9:16 — scale up more to fill height
        scale2 = target_h / new_h
        resized = resized.resized(lambda t: scale2)
        # Center crop to 1080x1920
        final_w = int(target_w * scale2)
        x_offset = (final_w - target_w) // 2
        resized = resized.cropped(x1=x_offset, x2=x_offset + target_w, y1=0, y2=target_h)
    elif new_h > target_h:
        # Crop height to fit
        y_offset = (new_h - target_h) // 2
        resized = resized.cropped(x1=0, x2=target_w, y1=y_offset, y2=y_offset + target_h)

    logger.info("Auto-zoom completato: %dx%d", resized.size[0], resized.size[1])
    return resized


def edit_video(
    avatar_video_path: Path,
    script: str,
    config: EditorConfig,
    output_dir: Path,
) -> Path:
    output_path = output_dir / "final.mp4"

    base = VideoFileClip(str(avatar_video_path))
    logger.info(
        "Video base caricato: %.1fs, %dx%d",
        base.duration, base.size[0], base.size[1],
    )

    # NOTE: auto-zoom rimosso. Usiamo solo avatar gia' in formato Reel verticale 1080x1920
    # selezionati dalla dashboard, quindi il video HeyGen e' gia' a schermo pieno.

    subtitle_clips = _create_subtitle_clips(
        avatar_video_path, base.duration, tuple(base.size), config
    )

    lower_third = _add_lower_third(config, base.duration)

    overlay_clips = [base] + subtitle_clips
    if lower_third is not None:
        overlay_clips.append(lower_third)

    composite = CompositeVideoClip(overlay_clips, size=base.size)

    mixed_audio = _add_background_music(base, config)
    if mixed_audio is not None:
        composite = composite.with_audio(mixed_audio)

    segments = []
    if config.intro_clip:
        intro_path = Path(config.intro_clip)
        if intro_path.exists():
            intro = VideoFileClip(str(intro_path))
            intro = intro.resized(base.size)
            segments.append(intro)
            logger.info("Intro aggiunto: %.1fs", intro.duration)

    segments.append(composite)

    if config.outro_clip:
        outro_path = Path(config.outro_clip)
        if outro_path.exists():
            outro = VideoFileClip(str(outro_path))
            outro = outro.resized(base.size)
            segments.append(outro)
            logger.info("Outro aggiunto: %.1fs", outro.duration)

    if len(segments) > 1:
        final = concatenate_videoclips(segments, method="compose")
    else:
        final = composite

    import os as _os
    cpu_count = max(2, (_os.cpu_count() or 4))
    logger.info("Export video con preset ultrafast (%d threads)...", cpu_count)
    final.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=30,
        bitrate="6000k",
        preset="ultrafast",
        threads=cpu_count,
        ffmpeg_params=["-movflags", "+faststart", "-tune", "fastdecode"],
        logger=None,
    )

    base.close()
    final.close()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Video finale esportato: %s (%.1f MB)", output_path, size_mb)

    return output_path
