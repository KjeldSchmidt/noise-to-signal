"""Fetch embeddings, compute report, write S3 artifacts."""

from __future__ import annotations

import logging
from typing import Any

from n2s_web_client import iter_article_embeddings, list_themes

from compute import compute_report
from s3_artifacts import utc_now_iso, write_latest, write_status

logger = logging.getLogger(__name__)


def run_analysis() -> dict[str, Any]:
    started = utc_now_iso()
    write_status("running", started_at=started, finished_at=None, error="")
    try:
        themes = list_themes()
        rows = iter_article_embeddings(page_size=200)
        logger.info("loaded %s embedded articles, %s themes", len(rows), len(themes))
        finished = utc_now_iso()
        report = compute_report(rows, themes, generated_at=finished)
        write_latest(report)
        write_status("ready", started_at=started, finished_at=finished, error="")
        return {
            "ok": True,
            "article_count": report["article_count"],
            "theme_count": len(report["themes"]),
        }
    except Exception as exc:
        logger.exception("theme_analysis failed")
        write_status(
            "failed",
            started_at=started,
            finished_at=utc_now_iso(),
            error=str(exc)[:500],
        )
        return {"ok": False, "error": str(exc)[:500]}
