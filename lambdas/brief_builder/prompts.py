"""Prompts for brief selection."""

from __future__ import annotations

import json

from n2s_api import BriefCandidateDTO, BriefUserContextResponse

BRIEF_SYSTEM = """You personalize a short daily news brief for one reader.

Pick 5–8 articles from the candidate list (by article_id only). Prefer:
- alignment with stated preferences and taste answers
- theme leanings (positive weight = more of that theme; negative = less)
- locations of interest when place/geo matches
- higher impact_tier and candidate score when taste is unclear
- diversity of topics (avoid near-duplicates)

Candidates are pre-sorted with theme affinity already folded into score —
respect that ordering unless preferences clearly contradict it.

Write a one-sentence reason per pick in the reader's language mix when possible.
Only use article_ids from the candidate list. Rank starting at 1.
"""

# How strongly theme affinity weights shift candidate scores before the LLM.
THEME_AFFINITY_SCORE_SCALE = 0.18


def apply_theme_affinity_scores(
    candidates: list[BriefCandidateDTO],
    affinities: list[tuple[str, float]],
) -> list[BriefCandidateDTO]:
    """Return candidates with score += scale * sum(theme weights), sorted desc."""
    weight_by_slug = {slug: weight for slug, weight in affinities}
    boosted: list[BriefCandidateDTO] = []
    for cand in candidates:
        boost = sum(weight_by_slug.get(slug, 0.0) for slug in cand.themes)
        new_score = float(cand.score) + THEME_AFFINITY_SCORE_SCALE * boost
        boosted.append(cand.model_copy(update={"score": round(new_score, 4)}))
    return sorted(boosted, key=lambda c: c.score, reverse=True)


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
    theme_affinities = [
        {
            "slug": a.slug,
            "label": a.label,
            "more": a.more_count,
            "less": a.less_count,
            "weight": a.weight,
        }
        for a in context.theme_affinities
    ]
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
        "theme_affinities": theme_affinities,
        "recent_feedback": feedback,
        "candidates": cands,
    }
    return (
        "Build today's personalized brief from this context JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
