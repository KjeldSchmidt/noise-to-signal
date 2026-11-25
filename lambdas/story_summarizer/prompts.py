"""Prompts for non-personal story-thread summaries."""

from __future__ import annotations

import json

from n2s_api import StoryThreadSummaryContextResponse

SUMMARY_SYSTEM = """You write a neutral, non-personal digest of a developing news story thread.

Rules:
- 2–4 short sentences in clear English
- Cover what happened, who is involved, and the latest development
- No reader addressing, no opinions, no speculation beyond the sources
- Do not invent facts that are not supported by the provided articles
- Prefer concrete details over vague phrasing
"""


def build_summary_user_message(context: StoryThreadSummaryContextResponse) -> str:
    payload = {
        "thread_label": context.label,
        "articles": [
            {
                "title": row.title,
                "source": row.source,
                "published_at": row.published_at,
                "summary": (row.summary or "")[:500],
            }
            for row in context.articles[:12]
        ],
    }
    return (
        "Summarize this story thread from the article list JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
