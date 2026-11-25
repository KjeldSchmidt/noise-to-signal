"""User-agnostic article/thread importance: tier weight × time decay (+ coverage)."""

from __future__ import annotations

import math
from datetime import datetime

from news.models import Article, ImpactTier

HALF_LIFE_HOURS = 36.0
COVERAGE_BOOST_K = 0.45

TIER_WEIGHTS: dict[str, float] = {
    ImpactTier.COMMERCIAL: 0.15,
    ImpactTier.EPHEMERAL: 0.4,
    "": 0.35,
    ImpactTier.NOTABLE: 1.0,
    ImpactTier.MAJOR: 2.5,
}


def tier_weight(tier: str) -> float:
    """Map impact_tier (including blank) to a ranking weight."""
    return TIER_WEIGHTS.get(tier, TIER_WEIGHTS[""])


def article_impact_score(
    tier: str,
    published_at: datetime,
    *,
    now: datetime,
) -> float:
    """Decayed importance for a single article."""
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    return tier_weight(tier) * (0.5 ** (age_hours / HALF_LIFE_HOURS))


def score_article(article: Article, *, now: datetime) -> float:
    """Decayed importance for a persisted article row."""
    return article_impact_score(article.impact_tier, article.published_at, now=now)


def thread_impact_score(members: list[Article], *, now: datetime) -> float:
    """Max member score with a log-damped boost from additional coverage."""
    scores = [score_article(member, now=now) for member in members]
    if not scores:
        return 0.0
    base = max(scores)
    if base <= 0.0:
        return 0.0
    others = sum(scores) - base
    return base * (1.0 + COVERAGE_BOOST_K * math.log1p(others / base))


def blend_relevance_impact(
    *,
    similarity: float | None,
    impact: float,
) -> float:
    """Combine retrieval relevance with importance for search-style ranking.

    Missing similarity (e.g. title hit without an embedding query) is treated as
    full relevance so impact still differentiates among lexical matches.
    """
    relevance = 1.0 if similarity is None else max(0.0, float(similarity))
    return relevance * max(0.0, impact)
