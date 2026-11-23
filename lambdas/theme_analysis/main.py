"""Lambda entry for theme_analysis."""

from __future__ import annotations

import logging
from typing import Any

from run import run_analysis

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


def handler(
    event: dict[str, Any] | str | bytes | None = None, context: object = None
) -> dict[str, object]:
    """Event payload is ignored; always runs a full analysis pass."""
    _ = event, context
    try:
        result = run_analysis()
        return {k: v for k, v in result.items()}
    except Exception as exc:
        logger.exception("theme_analysis handler failed")
        return {"ok": False, "error": str(exc)[:500]}
