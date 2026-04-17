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

logger = logging.getLogger(__name__)


def _split_script_into_chunks(script: str, words_per_chunk: int) -> list[str]:
    words = script.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i : i + words_per_chunk])
        chunks.append(chunk)
    return chunks


def _render_subtitle_nicktrading(
    text: str,
    video_width: int,
    video_height: int,
    font_path: str,
    font_size: int,
) -> np.ndarray:
    """Render EXACT nicktrading_ style subtitle.

    Style details (from frame analysis):
    - Font: Bebas Neue or Impact, very bold, condensed
    - ALL CAPS
    - First word of each chunk: RED rounded-rectangle box (#E8163C) behind it, white text
    - Remaining words: white text with thick black stroke
    - Centered horizontally
    - Very large text, fills most of the width
    - Box has generous padding and rounded corners
    """
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    words = text.upper().split()
    if not words:
        return np.zeros((10, 10, 4), dtype=np.uint8)

    space_width = font.getlength(" ")

    # Measure each word
    word_data = []
    for w in words:
        bbox = font.getbbox(w)
        w_width = bbox[2] - bbox[0]
        w_height = bbox[3] - bbox[1]
        y_offset = bbox[1]  # top offset for proper vertical alignment
        word_data.append((w, w_width, w_height, y_offset))

    max_height = max(wh for _, _, wh, _ in word_data)

    # The first word gets the red box
    # Calculate total width
    total_text_width = sum(wd[1] for wd in word_data) + space_width * (len(words) - 1)

    # Box padding for the highlighted word
    box_pad_x = 12
    box_pad_y = 8
    box_radius = 10

    # Stroke width for non-highlighted words
    stroke_w = 5

    # Image dimensions - generous to fit everything
    extra = box_pad_x * 2 + stroke_w * 2 + 40
    img_width = int(total_text_width + extra)
    img_height = int(max_height + box_pad_y * 2 + stroke_w * 2 + 30)

    img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Start x centered
    x_start = (img_width - total_text_width) / 2
    x = x_start
    y_text = stroke_w + box_pad_y + 5

    for idx, (word, w_width, w_height, y_off) in enumerate(word_data):
        # First word gets the red box
        if idx == 0:
            # Draw red rounded rectangle
            rx1 = x - box_pad_x
            ry1 = y_text - box_pad_y + 2
            rx2 = x + w_width + box_pad_x
            ry2 = y_text + max_height + box_pad_y - 2
            draw.rounded_rectangle(
                [rx1, ry1, rx2, ry2],
                radius=box_radius,
                fill=(232, 22, 60, 255),  # #E8163C — exact nicktrading_ red
            )
            # White text on red box
            draw.text((x, y_text), word, font=font, fill=(255, 255, 255, 255))
        else:
            # Black stroke — thick, draw in a circle pattern
            for dx in range(-stroke_w, stroke_w + 1):
                for dy in range(-stroke_w, stroke_w + 1):
                    # Circle pattern for smoother stroke
                    if dx * dx + dy * dy <= stroke_w * stroke_w:
                        draw.text(
                            (x + dx, y_text + dy), word, font=font,
                            fill=(0, 0, 0, 255),
                        )
            # White text on top
            draw.text((x, y_text), word, font=font, fill=(255, 255, 255, 255))

        x += w_width + space_width

    return np.array(img)


def _create_subtitle_clips(
    script: str,
    video_duration: float,
    video_size: tuple[int, int],
    config: EditorConfig,
) -> list[ImageClip]:
    """Create nicktrading_ exact style subtitle clips."""
    sub_config = config.subtitle
    chunks = _split_script_into_chunks(script, sub_config.words_per_subtitle)

    if not chunks:
        return []

    duration_per_chunk = video_duration / len(chunks)
    clips = []

    for i, text in enumerate(chunks):
        img_array = _render_subtitle_nicktrading(
            text=text,
            video_width=video_size[0],
            video_height=video_size[1],
            font_path=sub_config.font_path,
            font_size=sub_config.font_size,
        )

        clip = ImageClip(img_array, transparent=True)
        clip = clip.with_duration(duration_per_chunk)
        clip = clip.with_start(i * duration_per_chunk)
        # Position: center of screen, slightly below middle (like nicktrading_ ~60%)
        clip = clip.with_position(("center", 0.58), relative=True)

        clips.append(clip)

    logger.info("Creati %d sottotitoli nicktrading_ (%.2fs ciascuno)", len(clips), duration_per_chunk)
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

    # Auto-zoom: remove black bars and fill 9:16
    base = _auto_zoom_vertical(base)

    subtitle_clips = _create_subtitle_clips(
        script, base.duration, tuple(base.size), config
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

    final.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=30,
        bitrate="8000k",
        preset="medium",
        ffmpeg_params=["-movflags", "+faststart"],
        logger=None,
    )

    base.close()
    final.close()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Video finale esportato: %s (%.1f MB)", output_path, size_mb)

    return output_path
