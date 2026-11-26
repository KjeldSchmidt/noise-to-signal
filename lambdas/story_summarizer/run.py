"""Generate and persist multilingual story-thread summaries."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from n2s_api import (
    StorySummarizerRequest,
    StoryThreadMultilangDigest,
    StoryThreadSummaryUpdateRequest,
)
from n2s_web_client import get_story_thread_summary_context, update_story_thread_summary

from llm_model import get_summary_model
from prompts import SUMMARY_SYSTEM, build_summary_user_message

logger = logging.getLogger(__name__)


def run_summary(story_thread_id: int) -> dict[str, Any]:
    context = get_story_thread_summary_context(story_thread_id)
    if not context.articles:
        return {"ok": False, "error": "no articles", "story_thread_id": story_thread_id}

    model = get_summary_model().with_structured_output(StoryThreadMultilangDigest)
    message = build_summary_user_message(context)
    digest = model.invoke([SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=message)])
    if not isinstance(digest, StoryThreadMultilangDigest):
        digest = StoryThreadMultilangDigest.model_validate(digest)

    updated = update_story_thread_summary(
        StoryThreadSummaryUpdateRequest(
            story_thread_id=story_thread_id,
            localizations=digest.localizations,
        )
    )
    return {
        "ok": True,
        "story_thread_id": updated.story_thread_id,
        "summary_chars": updated.summary_chars,
        "localization_count": updated.localization_count,
        "summarized_at": updated.summarized_at,
    }


def dispatch(req: StorySummarizerRequest) -> dict[str, Any]:
    try:
        return run_summary(req.story_thread_id)
    except Exception as exc:
        logger.exception("story_summarizer failed for thread=%s", req.story_thread_id)
        return {
            "ok": False,
            "story_thread_id": req.story_thread_id,
            "error": str(exc)[:500],
        }
