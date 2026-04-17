"""Stage 2: Generate Italian reel script using Claude API."""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .config_loader import ScriptwriterConfig
from .scraper import Article

logger = logging.getLogger(__name__)


def _build_news_block(articles: list[Article]) -> str:
    """Format articles into a text block for the prompt."""
    lines = []
    for i, art in enumerate(articles, 1):
        lines.append(f"{i}. [{art.source}] {art.title}")
        if art.summary:
            lines.append(f"   {art.summary[:300]}")
        lines.append("")
    return "\n".join(lines)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _call_claude(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_prompt: str,
    config: ScriptwriterConfig,
) -> str:
    """Call Claude API with retry logic and prompt caching."""
    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text.strip()

    # Log usage
    usage = response.usage
    logger.info(
        "Claude usage: input=%d, output=%d, cache_read=%s, cache_create=%s",
        usage.input_tokens,
        usage.output_tokens,
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
    )

    return text


def generate_script(
    articles: list[Article],
    config: ScriptwriterConfig,
    api_key: str,
) -> str:
    """Generate an Italian reel script from news articles."""
    client = anthropic.Anthropic(api_key=api_key)

    word_count = config.target_word_count
    duration = config.target_duration_seconds

    # Build system prompt with template variables
    system_prompt = config.system_prompt.format(
        duration=duration,
        tone=config.tone,
        word_count=word_count,
    )

    # Build user prompt
    news_block = _build_news_block(articles)
    user_prompt = (
        f"Ecco le notizie di oggi su finanza e crypto. "
        f"Scrivi uno script di circa {word_count} parole per un reel di {duration} secondi.\n\n"
        f"NOTIZIE:\n{news_block}"
    )

    script = _call_claude(client, system_prompt, user_prompt, config)

    # Validate word count
    actual_words = len(script.split())
    logger.info("Script generato: %d parole (target: %d)", actual_words, word_count)

    if actual_words > word_count * 1.3:
        logger.warning(
            "Script troppo lungo (%d parole), rigenero con vincolo più stretto",
            actual_words,
        )
        user_prompt += (
            f"\n\nIMPORTANTE: lo script precedente era troppo lungo ({actual_words} parole). "
            f"Riscrivi in massimo {word_count} parole. Sii più conciso."
        )
        script = _call_claude(client, system_prompt, user_prompt, config)
        actual_words = len(script.split())
        logger.info("Script rigenerato: %d parole", actual_words)

    return script


def save_script(script: str, output_dir: Path) -> Path:
    """Save script to text file."""
    path = output_dir / "script.txt"
    path.write_text(script, encoding="utf-8")
    logger.info("Script salvato in %s", path)
    return path


def load_script(output_dir: Path) -> str:
    """Load script from a previous run."""
    path = output_dir / "script.txt"
    return path.read_text(encoding="utf-8")
