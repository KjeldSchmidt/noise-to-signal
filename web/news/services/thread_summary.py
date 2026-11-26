"""Non-personal story-thread AI summary freshness and invoke helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone
from n2s_api import THREAD_SUMMARY_TTL, StorySummarizerRequest

from news.models import StoryThread

logger = logging.getLogger(__name__)
_STUB_SUMMARY = (
    "Coverage continues on this developing story across multiple sources. "
    "(Local stub summary — configure STORY_SUMMARIZER_FUNCTION_NAME for live digests.)"
)


def thread_summary_is_fresh(
    thread: StoryThread,
    *,
    now: datetime | None = None,
) -> bool:
    """True when a non-empty summary was written inside the TTL window."""
    if not (thread.summary or "").strip() or thread.summarized_at is None:
        return False
    clock = now or timezone.now()
    return thread.summarized_at >= clock - THREAD_SUMMARY_TTL


def should_refresh_thread_summary(
    thread: StoryThread,
    *,
    now: datetime | None = None,
) -> bool:
    return not thread_summary_is_fresh(thread, now=now)


def _lambda_client() -> Any:
    import boto3

    return boto3.client(
        "lambda",
        region_name=getattr(settings, "AWS_REGION", None)
        or getattr(settings, "BEDROCK_REGION", None)
        or None,
    )


def _stub_write_summary(thread_id: int) -> None:
    thread = StoryThread.objects.filter(pk=thread_id).first()
    if thread is None:
        return
    thread.summary = _STUB_SUMMARY
    thread.summarized_at = timezone.now()
    thread.save(update_fields=["summary", "summarized_at", "updated_at"])


def invoke_story_summarizer(story_thread_id: int) -> None:
    """Event-invoke the story_summarizer worker (or DEBUG stub)."""
    req = StorySummarizerRequest(story_thread_id=story_thread_id)
    function_name = (getattr(settings, "STORY_SUMMARIZER_FUNCTION_NAME", None) or "").strip()
    if function_name:
        _lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=req.model_dump_json().encode("utf-8"),
        )
        return

    if settings.DEBUG:
        _stub_write_summary(story_thread_id)
        return

    logger.error("STORY_SUMMARIZER_FUNCTION_NAME is not configured")


def maybe_invoke_thread_summary(story_thread_id: int) -> bool:
    """
    Kick a refresh when the thread exists and its summary is missing/stale.

    Returns True when an invoke (or DEBUG stub) was attempted.
    """
    thread = StoryThread.objects.filter(pk=story_thread_id).first()
    if thread is None:
        return False
    if not should_refresh_thread_summary(thread):
        return False
    try:
        invoke_story_summarizer(thread.id)
    except Exception:
        logger.exception("Failed to invoke story summarizer for thread=%s", story_thread_id)
        return False
    return True
