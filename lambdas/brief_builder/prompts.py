"""Prompts for brief selection."""

from __future__ import annotations

import json

from n2s_api import BriefCandidateDTO, BriefUserContextResponse

BRIEF_SYSTEM = """You personalize a short daily news brief for one reader.

Pick 5–8 articles from the candidate list (by article_id only). Prefer:
- alignment with stated preferences and taste answers
- locations of interest when place/geo matches
- higher impact_tier and candidate score when taste is unclear
- diversity of topics (avoid near-duplicates)

Write a one-sentence reason per pick in the reader's language mix when possible.
Only use article_ids from the candidate list. Rank starting at 1.
"""


def build_evaluate_user_message(
    *,
    preferences: list[str],
    context: BriefUserContextResponse,
    candidates: list[BriefCandidateDTO],
) -> str:
    locs = [
        {
            "label": loc.label,
            "country_code": loc.country_code,
            "admin1": loc.admin1,
            "locality": loc.locality,
        }
        for loc in context.locations
    ]
    taste = [{"q": t.question, "a": t.answer} for t in context.taste_answers]
    feedback = [{"title": f.title, "verdict": f.verdict} for f in context.recent_feedback[:15]]
    cands = [
        {
            "article_id": c.article_id,
            "title": c.title,
            "summary": c.summary[:400],
            "source": c.source,
            "impact_tier": c.impact_tier,
            "story_label": c.story_label,
            "place_label": c.place_label,
            "country_code": c.country_code,
            "themes": c.themes,
            "score": c.score,
        }
        for c in candidates
    ]
    payload = {
        "preferences": preferences,
        "languages": context.languages,
        "locations": locs,
        "taste_answers": taste,
        "recent_feedback": feedback,
        "candidates": cands,
    }
    return (
        "Build today's personalized brief from this context JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
