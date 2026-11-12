"""Invoke the news_chat worker (Lambda sync, or DEBUG stub)."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from n2s_api import ChatWorkerRequest, ChatWorkerResponse

logger = logging.getLogger(__name__)


def _stub_response(req: ChatWorkerRequest) -> ChatWorkerResponse:
    """Local/dev fallback when NEWS_CHAT_FUNCTION_NAME is unset."""
    titles = [c.title for c in req.chunks if c.title][:5]
    if titles:
        listed = "; ".join(titles)
        reply = (
            f"(Local chat stub) You asked about this context covering: {listed}. "
            "Deploy the news_chat worker and set NEWS_CHAT_FUNCTION_NAME for real answers."
        )
    else:
        reply = (
            "(Local chat stub) No articles in scope yet. "
            "Deploy news_chat and set NEWS_CHAT_FUNCTION_NAME for real answers."
        )
    return ChatWorkerResponse(refused=False, reason="ok", reply=reply, message="")


def _invoke_lambda(req: ChatWorkerRequest, function_name: str) -> ChatWorkerResponse:
    import boto3

    client = boto3.client(
        "lambda",
        region_name=getattr(settings, "AWS_REGION", None)
        or getattr(settings, "BEDROCK_REGION", None)
        or None,
    )
    payload = req.model_dump_json().encode("utf-8")
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=payload,
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        logger.error("news_chat Lambda error: %s", raw[:500])
        return ChatWorkerResponse(
            refused=True,
            reason="off_topic",
            reply="",
            message="Chat is temporarily unavailable. Please try again.",
        )
    data: dict[str, Any] = json.loads(raw)
    return ChatWorkerResponse.model_validate(data)


def invoke_news_chat(req: ChatWorkerRequest) -> ChatWorkerResponse:
    """
    Call the news_chat worker.

    Production: sync Lambda invoke via NEWS_CHAT_FUNCTION_NAME.
    DEBUG without a function name: deterministic stub for UI work.
    """
    function_name = (getattr(settings, "NEWS_CHAT_FUNCTION_NAME", None) or "").strip()
    if function_name:
        return _invoke_lambda(req, function_name)

    if settings.DEBUG:
        return _stub_response(req)

    logger.error("NEWS_CHAT_FUNCTION_NAME is not configured")
    return ChatWorkerResponse(
        refused=True,
        reason="off_topic",
        reply="",
        message="Chat is not configured on this environment.",
    )
