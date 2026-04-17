"""Main pipeline orchestrator — wires all 5 stages together."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from .config_loader import AppConfig, load_config

logger = logging.getLogger(__name__)

STAGES = ["scraper", "scriptwriter", "avatar", "editor", "publisher"]


def _setup_run_dir(config: AppConfig, run_date: date | None = None) -> Path:
    """Create and return the output directory for this run."""
    if run_date is None:
        run_date = date.today()
    run_dir = Path(config.pipeline.output_dir) / run_date.isoformat()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _save_metadata(
    run_dir: Path,
    publish_id: str | None,
    dry_run: bool,
    error: str | None = None,
) -> None:
    """Save run metadata."""
    meta = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "publish_id": publish_id,
        "status": "error" if error else "success",
        "error": error,
    }
    path = run_dir / "metadata.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def run_pipeline(
    dry_run: bool | None = None,
    from_stage: str | None = None,
    run_date: date | None = None,
) -> None:
    """Execute the full pipeline or resume from a specific stage."""
    config = load_config()

    if dry_run is None:
        dry_run = config.pipeline.dry_run

    run_dir = _setup_run_dir(config, run_date)
    start_index = STAGES.index(from_stage) if from_stage else 0

    logger.info("=" * 60)
    logger.info(
        "POWEREEL pipeline avviata | dry_run=%s | from=%s | dir=%s",
        dry_run,
        from_stage or "inizio",
        run_dir,
    )
    logger.info("=" * 60)

    publish_id = None
    error_msg = None

    try:
        # ── Stage 1: Scraping ─────────────────────────────────────────
        if start_index <= 0:
            logger.info("── Stage 1/5: Scraping notizie ──")
            from .scraper import save_articles, scrape_news

            articles = scrape_news(config.scraper)
            save_articles(articles, run_dir)
        else:
            from .scraper import load_articles

            articles = load_articles(run_dir)
            logger.info("Articoli caricati da run precedente: %d", len(articles))

        # ── Stage 2: Script generation ────────────────────────────────
        if start_index <= 1:
            logger.info("── Stage 2/5: Generazione script ──")
            from .scriptwriter import generate_script, save_script

            script = generate_script(
                articles, config.scriptwriter, config.anthropic_api_key
            )
            save_script(script, run_dir)
        else:
            from .scriptwriter import load_script

            script = load_script(run_dir)
            logger.info("Script caricato da run precedente")

        # ── Stage 3: Avatar video ─────────────────────────────────────
        if start_index <= 2:
            logger.info("── Stage 3/5: Generazione video avatar ──")
            from .avatar import generate_avatar_video

            avatar_path = generate_avatar_video(
                script, config.heygen, config.heygen_api_key, run_dir
            )
        else:
            avatar_path = run_dir / "avatar_raw.mp4"
            if not avatar_path.exists():
                raise FileNotFoundError(f"Video avatar non trovato: {avatar_path}")
            logger.info("Video avatar caricato da run precedente")

        # ── Stage 4: Editing ──────────────────────────────────────────
        if start_index <= 3:
            logger.info("── Stage 4/5: Post-produzione video ──")
            from .editor import edit_video

            final_path = edit_video(avatar_path, script, config.editor, run_dir)
        else:
            final_path = run_dir / "final.mp4"
            if not final_path.exists():
                raise FileNotFoundError(f"Video finale non trovato: {final_path}")
            logger.info("Video finale caricato da run precedente")

        # ── Stage 5: Publishing ───────────────────────────────────────
        if start_index <= 4:
            if dry_run:
                logger.info("── Stage 5/5: SKIP (dry-run) ──")
                logger.info("Video finale pronto: %s", final_path)
            else:
                logger.info("── Stage 5/5: Pubblicazione Instagram ──")
                from .auth import check_and_refresh_token
                from .publisher import publish_to_instagram

                # Refresh token if needed
                token = check_and_refresh_token(
                    config.meta_access_token,
                    config.meta_app_id,
                    config.meta_app_secret,
                )

                publish_id = publish_to_instagram(
                    final_path,
                    articles,
                    config.publisher,
                    config.instagram_business_account_id,
                    token,
                )

        # ── Cleanup ───────────────────────────────────────────────────
        from .storage import cleanup_old_runs

        cleanup_old_runs(config.pipeline.output_dir, config.pipeline.max_days_kept)

        logger.info("=" * 60)
        logger.info("Pipeline completata con successo!")
        logger.info("=" * 60)

    except Exception as e:
        error_msg = str(e)
        logger.exception("Pipeline FALLITA: %s", e)
        raise
    finally:
        _save_metadata(run_dir, publish_id, dry_run, error_msg)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="POWEREEL - Pipeline automatica per reel AI")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Genera il video senza pubblicare su Instagram",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Forza la pubblicazione (override del config)",
    )
    parser.add_argument(
        "--from-stage",
        choices=STAGES,
        default=None,
        help="Riprendi da uno stage specifico (usa output precedenti)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Data della run (YYYY-MM-DD), default: oggi",
    )

    args = parser.parse_args()

    dry_run = None
    if args.dry_run:
        dry_run = True
    elif args.no_dry_run:
        dry_run = False

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    try:
        run_pipeline(dry_run=dry_run, from_stage=args.from_stage, run_date=run_date)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
