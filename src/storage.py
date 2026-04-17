"""Cleanup old output directories."""

from __future__ import annotations

import logging
import shutil
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_old_runs(output_dir: str, max_days_kept: int) -> None:
    """Delete output folders older than max_days_kept days."""
    output_path = Path(output_dir)
    if not output_path.exists():
        return

    cutoff = date.today() - timedelta(days=max_days_kept)
    deleted = 0

    for folder in output_path.iterdir():
        if not folder.is_dir():
            continue
        try:
            folder_date = date.fromisoformat(folder.name)
        except ValueError:
            continue  # Skip non-date folders

        if folder_date < cutoff:
            shutil.rmtree(folder)
            logger.info("Cartella eliminata: %s", folder)
            deleted += 1

    if deleted:
        logger.info("Pulizia completata: %d cartelle eliminate", deleted)
