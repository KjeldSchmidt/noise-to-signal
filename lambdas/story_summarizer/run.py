"""Generate and persist a story-thread summary."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from n2s_api import StorySummarizerRequest, StoryThreadSummaryUpdateRequest
from n2s_web_client import get_story_thread_summary_context, update_story_thread_summary

from llm_model import get_summary_model
from prompts import SUMMARY_SYSTEM, build_summary_user_message

logger = logging.getLogger(__name__)


def run_summary(story_thread_id: int) -> dict[str, Any]:
    context = get_story_thread_summary_context(story_thread_id)
    if not context.articles:
        return {"ok": False, "error": "no articles", "story_thread_id": story_thread_id}

    model = get_summary_model()
    message = build_summary_user_message(context)
    result = model.invoke([SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=message)])
    content = getattr(result, "content", result)
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(str(part["text"]))
            else:
                text_parts.append(str(part))
        summary = " ".join(text_parts).strip()
    else:
        summary = str(content or "").strip()

    if not summary:
        return {"ok": False, "error": "empty model summary", "story_thread_id": story_thread_id}

    summary = summary[:4000]
    updated = update_story_thread_summary(
        StoryThreadSummaryUpdateRequest(story_thread_id=story_thread_id, summary=summary)
    )
    return {
        "ok": True,
        "story_thread_id": updated.story_thread_id,
        "summary_chars": updated.summary_chars,
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
