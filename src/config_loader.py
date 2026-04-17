"""Configuration loader with Pydantic validation."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Project root: two levels up from this file (src/config_loader.py -> POWEREEL/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Pydantic models ──────────────────────────────────────────────────────────


class FeedConfig(BaseModel):
    name: str
    url: str
    lang: str = "en"


class ScraperConfig(BaseModel):
    feeds: list[FeedConfig]
    max_articles_per_feed: int = 5
    max_total_articles: int = 10


class ScriptwriterConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    target_duration_seconds: int = 45
    language: str = "it"
    tone: str = "coinvolgente, diretto, informativo, leggermente informale"
    system_prompt: str = ""

    @property
    def target_word_count(self) -> int:
        """~130 Italian words per minute."""
        return int(self.target_duration_seconds * 130 / 60)


class HeyGenConfig(BaseModel):
    avatar_id: str = ""
    voice_id: str = ""
    video_width: int = 1080
    video_height: int = 1920
    poll_interval_seconds: int = 15
    poll_max_attempts: int = 40


class SubtitleConfig(BaseModel):
    font_path: str = "./assets/fonts/Montserrat-Bold.ttf"
    font_size: int = 58
    font_color: str = "#FFFFFF"
    accent_color: str = "#FF0000"
    stroke_color: str = "#000000"
    stroke_width: int = 4
    position: str = "bottom"
    max_chars_per_line: int = 25
    words_per_subtitle: int = 3
    uppercase: bool = True


class BackgroundMusicConfig(BaseModel):
    path: str = "./assets/music/default_bg.mp3"
    volume: float = 0.08


class LowerThirdConfig(BaseModel):
    image: Optional[str] = None
    duration_seconds: int = 5
    position: list[int] = [540, 1600]


class EditorConfig(BaseModel):
    subtitle: SubtitleConfig = SubtitleConfig()
    background_music: BackgroundMusicConfig = BackgroundMusicConfig()
    intro_clip: Optional[str] = None
    outro_clip: Optional[str] = None
    lower_third: LowerThirdConfig = LowerThirdConfig()


class PublisherConfig(BaseModel):
    caption_template: str = ""
    max_hashtags: int = 30


class PipelineConfig(BaseModel):
    dry_run: bool = True
    schedule_cron: str = "0 8 * * *"
    output_dir: str = "./output"
    max_days_kept: int = 7


class AppConfig(BaseModel):
    pipeline: PipelineConfig = PipelineConfig()
    scraper: ScraperConfig
    scriptwriter: ScriptwriterConfig = ScriptwriterConfig()
    heygen: HeyGenConfig = HeyGenConfig()
    editor: EditorConfig = EditorConfig()
    publisher: PublisherConfig = PublisherConfig()

    # API keys (loaded from .env)
    anthropic_api_key: str = ""
    heygen_api_key: str = ""
    meta_access_token: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    instagram_business_account_id: str = ""


# ── Loader ────────────────────────────────────────────────────────────────────


def _setup_logging() -> None:
    """Configure logging to file + stderr."""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "powereel.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


# Need this import for RotatingFileHandler
import logging.handlers


def _check_ffmpeg() -> None:
    """Verify ffmpeg is installed and accessible."""
    # First check system PATH
    if shutil.which("ffmpeg") is not None:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )
        logger.info("ffmpeg trovato: %s", result.stdout.split("\n")[0])
        return

    # Fallback: check imageio_ffmpeg (bundled with moviepy)
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        logger.info("ffmpeg trovato via imageio_ffmpeg: %s", ffmpeg_path)
    except Exception:
        raise RuntimeError(
            "ffmpeg non trovato nel PATH e nemmeno via imageio_ffmpeg. "
            "Installalo con: choco install ffmpeg  oppure scaricalo da https://ffmpeg.org/"
        )


def load_config(
    config_path: Path | None = None,
    env_path: Path | None = None,
    check_ffmpeg: bool = True,
) -> AppConfig:
    """Load and validate the full application config."""
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if env_path is None:
        env_path = PROJECT_ROOT / "config" / ".env"

    # Load .env
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try root .env as fallback
        root_env = PROJECT_ROOT / ".env"
        if root_env.exists():
            load_dotenv(root_env)

    # Setup logging
    _setup_logging()

    # Load YAML
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Inject env vars
    raw["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    raw["heygen_api_key"] = os.getenv("HEYGEN_API_KEY", "")
    raw["meta_access_token"] = os.getenv("META_ACCESS_TOKEN", "")
    raw["meta_app_id"] = os.getenv("META_APP_ID", "")
    raw["meta_app_secret"] = os.getenv("META_APP_SECRET", "")
    raw["instagram_business_account_id"] = os.getenv(
        "INSTAGRAM_BUSINESS_ACCOUNT_ID", ""
    )

    config = AppConfig(**raw)

    # Check ffmpeg
    if check_ffmpeg:
        _check_ffmpeg()

    logger.info("Configurazione caricata da %s", config_path)
    return config
