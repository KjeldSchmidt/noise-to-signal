"""Lambda entry for brief_builder."""

from __future__ import annotations

import json
import logging
from typing import Any

from n2s_api import BriefBuilderRequest
from pydantic import ValidationError

from build import dispatch

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


def _parse_event(event: dict[str, Any] | list[Any] | str | bytes) -> BriefBuilderRequest:
    if isinstance(event, (bytes, bytearray)):
        event = event.decode("utf-8")
    if isinstance(event, str):
        payload = json.loads(event or "{}")
    elif isinstance(event, dict):
        # Direct invoke or API-style wrapper
        if "body" in event and isinstance(event["body"], str):
            payload = json.loads(event["body"] or "{}")
        else:
            payload = event
    else:
        raise ValueError("unsupported event type")
    return BriefBuilderRequest.model_validate(payload)


def handler(event: dict[str, Any] | str | bytes, context: object = None) -> dict[str, object]:
    try:
        req = _parse_event(event)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.error("invalid brief_builder event: %s", exc)
        return {"ok": False, "error": "invalid payload"}
    try:
        return dispatch(req)
    except Exception as exc:
        logger.exception("brief_builder failed")
        return {"ok": False, "error": str(exc)[:500]}
