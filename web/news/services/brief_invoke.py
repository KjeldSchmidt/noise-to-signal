"""Async Event-invoke the brief_builder worker (or DEBUG stub)."""

from __future__ import annotations

import logging

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


def invoke_brief_builder(req: BriefBuilderRequest) -> None:
    """
    Kick the brief_builder worker.

    Production: async Lambda Event invoke via BRIEF_BUILDER_FUNCTION_NAME.
    DEBUG without a function name: stub-complete for build actions.
    """
    function_name = (getattr(settings, "BRIEF_BUILDER_FUNCTION_NAME", None) or "").strip()
    if function_name:
        import boto3

        client = boto3.client(
            "lambda",
            region_name=getattr(settings, "AWS_REGION", None)
            or getattr(settings, "BEDROCK_REGION", None)
            or None,
        )
        client.invoke(
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
