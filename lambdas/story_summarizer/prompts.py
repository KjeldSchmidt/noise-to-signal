"""Prompts for non-personal multilingual story-thread summaries."""

from __future__ import annotations

import json

from n2s_api import PRODUCT_THREAD_LANGUAGES, StoryThreadSummaryContextResponse

SUMMARY_SYSTEM = """You write neutral, non-personal digests of a developing news story thread.

Return structured localizations for exactly these languages: en, fr, de.

Rules:
- For each language fill `label` (~3–6 word title) and `summary` (2–4 sentences)
- Write each language independently from the article sources (do NOT translate from English)
- Cover what happened, who is involved, and the latest development
- No reader addressing, no opinions, no speculation beyond the sources
- Do not invent facts that are not supported by the provided articles
- Prefer concrete details over vague phrasing
- Labels and summaries must be in the target language for that localization
"""


def build_summary_user_message(context: StoryThreadSummaryContextResponse) -> str:
    payload = {
        "thread_label": context.label,
        "required_languages": list(PRODUCT_THREAD_LANGUAGES),
        "articles": [
            {
                "title": row.title,
                "source": row.source,
                "language": row.language or "",
                "published_at": row.published_at,
                "summary": (row.summary or "")[:500],
            }
            for row in context.articles[:12]
        ],
    }
    return (
        "Summarize this story thread for each required language from the article list JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
