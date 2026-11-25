"""Prompts and candidate personalization for brief selection."""

from __future__ import annotations

import json
import math

from n2s_api import BriefCandidateDTO, BriefLocationDTO, BriefUserContextResponse
from n2s_api.places import places_match

BRIEF_SYSTEM = """You personalize a short daily news brief for one reader.

Pick 5–8 items from the candidate list by candidate_id only
(article:<id> or thread:<id>). Prefer:
- alignment with stated free-form preferences
- theme leanings (positive weight = more of that theme; negative = less)
- locations of interest when place/geo matches
- higher impact_tier and candidate score when preferences are unclear
- diversity of topics (avoid near-duplicates)
- story threads when they cover a developing event better than a single article

Candidates are pre-sorted with theme affinity and location match already
folded into score (multiplicative personalization on Stories impact) —
respect that ordering unless preferences clearly contradict it.

Write a one-sentence reason per pick in the reader's language mix when possible.
Only use candidate_id values from the candidate list. Rank starting at 1.
"""

# Bounded multiplicative personalization on Stories impact scores.
THEME_AFFINITY_ALPHA = 0.35
PLACE_MATCH_BETA = 0.45


def _best_place_match(cand: BriefCandidateDTO, locations: list[BriefLocationDTO]) -> float:
    if not locations:
        return 0.0
    best = 0.0
    for loc in locations:
        score = places_match(cand, loc)
        if score > best:
            best = score
    return best


def apply_personalization_scores(
    candidates: list[BriefCandidateDTO],
    affinities: list[tuple[str, float]],
    locations: list[BriefLocationDTO],
) -> list[BriefCandidateDTO]:
    """Return candidates with Stories score × theme_factor × place_factor, sorted desc.

    theme_factor = 1 + α * tanh(Σ theme weights)
    place_factor = 1 + β * max LOI match in [0, 1]
    Neutral prefs leave ordering unchanged.
    """
    weight_by_slug = {slug: weight for slug, weight in affinities}
    boosted: list[BriefCandidateDTO] = []
    for cand in candidates:
        theme_sum = sum(weight_by_slug.get(slug, 0.0) for slug in cand.themes)
        theme_factor = 1.0 + THEME_AFFINITY_ALPHA * math.tanh(theme_sum)
        place_factor = 1.0 + PLACE_MATCH_BETA * _best_place_match(cand, locations)
        new_score = float(cand.score) * theme_factor * place_factor
        boosted.append(cand.model_copy(update={"score": round(new_score, 4)}))
    return sorted(boosted, key=lambda c: c.score, reverse=True)


def apply_theme_affinity_scores(
    candidates: list[BriefCandidateDTO],
    affinities: list[tuple[str, float]],
) -> list[BriefCandidateDTO]:
    """Backward-compatible wrapper — theme only, no place boost."""
    return apply_personalization_scores(candidates, affinities, [])


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
            "geo_level": loc.geo_level,
        }
        for loc in context.locations
    ]
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
            "candidate_id": c.candidate_id,
            "kind": c.kind,
            "title": c.title,
            "summary": c.summary[:400],
            "source": c.source,
            "impact_tier": c.impact_tier,
            "story_label": c.story_label,
            "place_label": c.place_label,
            "country_code": c.country_code,
            "geo_level": c.geo_level,
            "admin1": c.admin1,
            "locality": c.locality,
            "themes": c.themes,
            "score": c.score,
            "article_count": c.article_count,
        }
        for c in candidates
    ]
    payload = {
        "preferences": preferences,
        "languages": context.languages,
        "locations": locs,
        "theme_affinities": theme_affinities,
        "candidates": cands,
    }
    return (
        "Build today's personalized brief from this context JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
