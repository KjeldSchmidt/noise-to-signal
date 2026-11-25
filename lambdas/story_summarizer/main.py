"""Lambda entry for story_summarizer."""

from __future__ import annotations

import json
import logging
from typing import Any

from n2s_api import StorySummarizerRequest
from pydantic import ValidationError

from run import dispatch

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


def _parse_event(event: dict[str, Any] | str | bytes | None) -> StorySummarizerRequest:
    if event is None:
        raise ValueError("missing event")
    if isinstance(event, (bytes, bytearray)):
        raw = event.decode("utf-8")
        return StorySummarizerRequest.model_validate_json(raw)
    if isinstance(event, str):
        return StorySummarizerRequest.model_validate_json(event)
    if isinstance(event, dict):
        # Direct invoke payload or API Gateway-style body
        body = event.get("body")
        if isinstance(body, str) and body.strip():
            return StorySummarizerRequest.model_validate_json(body)
        return StorySummarizerRequest.model_validate(event)
    raise ValueError(f"unsupported event type: {type(event)!r}")


def handler(
    event: dict[str, Any] | str | bytes | None = None, context: object = None
) -> dict[str, object]:
    _ = context
    try:
        req = _parse_event(event)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("invalid story_summarizer payload: %s", exc)
        return {"ok": False, "error": f"invalid payload: {exc}"[:500]}
    return dispatch(req)
