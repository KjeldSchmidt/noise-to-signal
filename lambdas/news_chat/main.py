"""news_chat — sync Lambda entrypoint (invoked by web)."""

from __future__ import annotations

import json
import logging
from typing import Any

from n2s_api import ChatWorkerRequest, ChatWorkerResponse
from pydantic import ValidationError

from chat import run_chat

logger = logging.getLogger(__name__)


def _parse_event(event: dict[str, Any] | str | bytes) -> ChatWorkerRequest:
    if isinstance(event, (str, bytes)):
        return ChatWorkerRequest.model_validate_json(event)
    if "body" in event and isinstance(event["body"], (str, bytes, dict)):
        body = event["body"]
        if isinstance(body, dict):
            return ChatWorkerRequest.model_validate(body)
        return ChatWorkerRequest.model_validate_json(body)
    return ChatWorkerRequest.model_validate(event)


def handler(event: dict[str, Any] | str | bytes, context: Any = None) -> dict[str, Any]:
    """
    RequestResponse invoke payload: ChatWorkerRequest JSON (dict or string body).

    Returns ChatWorkerResponse as a plain dict for the web boto3 client.
    """
    try:
        req = _parse_event(event)
    except ValidationError as exc:
        logger.warning("Invalid chat request: %s", exc)
        err = ChatWorkerResponse(
            refused=True,
            reason="off_topic",
            reply="",
            message="Invalid chat request.",
        )
        return err.model_dump()

    try:
        result = run_chat(req)
    except Exception:
        logger.exception("news_chat pipeline failed")
        err = ChatWorkerResponse(
            refused=True,
            reason="off_topic",
            reply="",
            message="Chat is temporarily unavailable. Please try again.",
        )
        return err.model_dump()

    return result.model_dump()


def handler_json(event: dict[str, Any] | str | bytes, context: Any = None) -> str:
    """JSON string variant for local adapters."""
    return json.dumps(handler(event, context))
