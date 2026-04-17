"""Scheduler entry point — runs the pipeline on a cron schedule."""

from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config_loader import load_config
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="POWEREEL Scheduler")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Esegui la pipeline immediatamente (senza aspettare il cron)",
    )
    args = parser.parse_args()

    config = load_config(check_ffmpeg=True)

    if args.now:
        logger.info("Esecuzione immediata richiesta (--now)")
        run_pipeline()
        return

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        CronTrigger.from_crontab(config.pipeline.schedule_cron),
        id="powereel_daily",
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler avviato — cron: %s", config.pipeline.schedule_cron
    )
    logger.info("Premi Ctrl+C per fermare")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler fermato")


if __name__ == "__main__":
    main()
