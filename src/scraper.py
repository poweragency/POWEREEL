"""Stage 1: RSS feed scraping for finance/crypto news."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
from pydantic import BaseModel

from .config_loader import ScraperConfig

logger = logging.getLogger(__name__)


class Article(BaseModel):
    title: str
    summary: str
    source: str
    url: str
    published: str  # ISO format


def _normalize_title(title: str) -> str:
    """Normalize title for deduplication."""
    return " ".join(title.lower().strip().split())


def _parse_feed(feed_url: str, feed_name: str, max_articles: int) -> list[Article]:
    """Parse a single RSS feed and return articles."""
    try:
        # Use httpx to fetch (feedparser's built-in fetch can be flaky)
        response = httpx.get(feed_url, timeout=15, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
    except Exception as e:
        logger.warning("Errore nel fetch del feed %s: %s", feed_name, e)
        return []

    articles = []
    for entry in feed.entries[:max_articles]:
        # Extract publication date
        published = ""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                published = dt.isoformat()
            except Exception:
                published = getattr(entry, "published", "")
        elif hasattr(entry, "published"):
            published = entry.published

        # Extract summary (prefer summary, fallback to description)
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        # Strip HTML tags simply
        if "<" in summary:
            from bs4 import BeautifulSoup

            summary = BeautifulSoup(summary, "lxml").get_text(separator=" ", strip=True)

        # Truncate very long summaries
        if len(summary) > 500:
            summary = summary[:500] + "..."

        articles.append(
            Article(
                title=getattr(entry, "title", "Senza titolo"),
                summary=summary,
                source=feed_name,
                url=getattr(entry, "link", ""),
                published=published,
            )
        )

    logger.info("Feed %s: %d articoli trovati", feed_name, len(articles))
    return articles


def _deduplicate(articles: list[Article]) -> list[Article]:
    """Remove duplicate articles by normalized title."""
    seen = set()
    unique = []
    for article in articles:
        key = _normalize_title(article.title)
        if key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def scrape_news(config: ScraperConfig) -> list[Article]:
    """Scrape all configured RSS feeds and return deduplicated articles."""
    all_articles: list[Article] = []

    for feed in config.feeds:
        articles = _parse_feed(feed.url, feed.name, config.max_articles_per_feed)
        all_articles.extend(articles)

    # Deduplicate
    all_articles = _deduplicate(all_articles)

    # Sort by publication date (most recent first)
    all_articles.sort(key=lambda a: a.published, reverse=True)

    # Limit total
    all_articles = all_articles[: config.max_total_articles]

    logger.info(
        "Totale articoli dopo dedup e filtro: %d", len(all_articles)
    )

    if not all_articles:
        raise RuntimeError("Nessun articolo trovato da nessun feed RSS!")

    return all_articles


def save_articles(articles: list[Article], output_dir: Path) -> Path:
    """Save articles to JSON file."""
    path = output_dir / "raw_news.json"
    data = [a.model_dump() for a in articles]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Articoli salvati in %s", path)
    return path


def load_articles(output_dir: Path) -> list[Article]:
    """Load articles from a previous run."""
    path = output_dir / "raw_news.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Article(**a) for a in data]
