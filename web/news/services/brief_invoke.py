"""Async Event-invoke / sync RequestResponse for the brief_builder worker."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.utils import timezone
from n2s_api import BriefBuilderRequest

from news.models import UserBrief, UserBriefItem
from news.services.brief import interim_ranked_items
from news.services.brief_context import user_for_brief

logger = logging.getLogger(__name__)


def _stub_complete_brief(user_id: int, brief_id: int) -> None:
    """Local/dev: mark brief ready from Stories-style interim ranking."""
    user = user_for_brief(user_id)
    brief = UserBrief.objects.get(pk=brief_id, user_id=user_id)
    ranked = interim_ranked_items(user, limit=8)
    UserBriefItem.objects.filter(brief=brief).delete()
    for idx, item in enumerate(ranked, start=1):
        UserBriefItem.objects.create(
            brief=brief,
            article=item.article,
            rank=idx,
            score=item.score,
            reason=item.reason,
        )
    brief.status = UserBrief.Status.READY
    brief.ready_at = timezone.now()
    brief.error = ""
    brief.save(update_fields=["status", "ready_at", "error", "updated_at"])


def _lambda_client() -> Any:
    import boto3

    return boto3.client(
        "lambda",
        region_name=getattr(settings, "AWS_REGION", None)
        or getattr(settings, "BEDROCK_REGION", None)
        or None,
    )


def invoke_brief_builder(req: BriefBuilderRequest) -> None:
    """
    Kick the brief_builder worker.

    Production: async Lambda Event invoke via BRIEF_BUILDER_FUNCTION_NAME.
    DEBUG without a function name: stub-complete for build actions.
    """
    function_name = (getattr(settings, "BRIEF_BUILDER_FUNCTION_NAME", None) or "").strip()
    if function_name:
        _lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=req.model_dump_json().encode("utf-8"),
        )
        return

    if settings.DEBUG:
        if req.action == "build" and req.brief_id is not None:
            _stub_complete_brief(req.user_id, req.brief_id)
        # preference recording is a no-op stub without AgentCore locally
        return

    logger.error("BRIEF_BUILDER_FUNCTION_NAME is not configured")


def invoke_brief_builder_sync(req: BriefBuilderRequest) -> dict[str, Any]:
    """
    RequestResponse invoke for list/delete preference actions.

    DEBUG without a function name: empty list / ok stubs.
    """
    function_name = (getattr(settings, "BRIEF_BUILDER_FUNCTION_NAME", None) or "").strip()
    if function_name:
        response = _lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=req.model_dump_json().encode("utf-8"),
        )
        payload = response.get("Payload")
        if payload is None:
            return {"ok": False, "error": "empty lambda payload"}
        raw = payload.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw or "{}")
        if isinstance(data, dict) and "body" in data and isinstance(data["body"], str):
            # API Gateway-style envelope from some handlers
            try:
                inner = json.loads(data["body"])
                if isinstance(inner, dict):
                    return inner
            except json.JSONDecodeError:
                pass
        if not isinstance(data, dict):
            return {"ok": False, "error": "unexpected lambda response"}
        return data

    if settings.DEBUG:
        if req.action == "list_preferences":
            return {"ok": True, "action": "list_preferences", "memories": []}
        if req.action == "delete_preference":
            return {"ok": True, "action": "delete_preference"}
        return {"ok": True, "action": req.action}

    logger.error("BRIEF_BUILDER_FUNCTION_NAME is not configured")
    return {"ok": False, "error": "brief builder not configured"}


def invoke_preference_record(user_id: int, preference_text: str) -> None:
    """Best-effort async preference write (does not block the request)."""
    text = (preference_text or "").strip()
    if not text:
        return
    try:
        invoke_brief_builder(
            BriefBuilderRequest(
                action="record_preference",
                user_id=user_id,
                preference_text=text[:2000],
            )
        )
    except Exception:
        logger.exception("Failed to enqueue preference record for user_id=%s", user_id)


def list_preference_memories(user_id: int) -> list[dict[str, str]]:
    out = invoke_brief_builder_sync(BriefBuilderRequest(action="list_preferences", user_id=user_id))
    memories = out.get("memories") if out.get("ok") else None
    if not isinstance(memories, list):
        return []
    cleaned: list[dict[str, str]] = []
    for row in memories:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "").strip()
        text = str(row.get("text") or "").strip()
        if rid:
            cleaned.append({"id": rid, "text": text})
    return cleaned


def delete_preference_memory(user_id: int, record_id: str) -> bool:
    rid = (record_id or "").strip()
    if not rid:
        return False
    out = invoke_brief_builder_sync(
        BriefBuilderRequest(
            action="delete_preference",
            user_id=user_id,
            memory_record_id=rid,
        )
    )
    return bool(out.get("ok"))
