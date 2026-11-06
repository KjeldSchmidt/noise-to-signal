"""Placeholder ranking — swap for the LangGraph runner later."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5

from django.contrib.auth.models import AbstractBaseUser

from news.models import Article, Feed, FeedMute, RelevanceFeedback
from news.services.feeds import catalog_feeds, enabled_feed_ids


@dataclass
class RankedItem:
    article: Article
    score: float
    reason: str
    show_to_user: bool


_REASON_TEMPLATES = (
    "Matches topics you've engaged with around {category}.",
    "Likely interesting given your recent relevance feedback.",
    "From {feed}, which sits near the top of your reading mix.",
    "Strong headline signal for someone following {category}.",
    "Placeholder rank: scored highly against your taste profile stub.",
)


def _stable_score(user_id: int, article_id: int) -> float:
    digest = md5(f"{user_id}:{article_id}".encode(), usedforsecurity=False).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    # Keep scores in a readable 0.35–0.95 band for the UI demo.
    return round(0.35 + raw * 0.60, 2)


def _reason_for(user_id: int, article: Article) -> str:
    idx = int(
        md5(f"reason:{user_id}:{article.id}".encode(), usedforsecurity=False).hexdigest(),
        16,
    ) % len(_REASON_TEMPLATES)
    return _REASON_TEMPLATES[idx].format(
        category=article.feed.category or "general news",
        feed=article.feed.title,
    )


def rank_items(user: AbstractBaseUser, articles: list[Article] | None = None) -> list[RankedItem]:
    """Return placeholder-ranked articles for the user's enabled feeds."""
    if articles is None:
        feed_ids = enabled_feed_ids(user)
        articles = list(
            Article.objects.filter(feed_id__in=feed_ids)
            .select_related("feed")
            .order_by("-published_at")[:40]
        )

    judged = set(
        RelevanceFeedback.objects.filter(user=user).values_list("article_id", flat=True)
    )

    ranked: list[RankedItem] = []
    for article in articles:
        if article.id in judged:
            continue
        score = _stable_score(user.pk, article.pk)
        ranked.append(
            RankedItem(
                article=article,
                score=score,
                reason=_reason_for(user.pk, article),
                show_to_user=score >= 0.55,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return [item for item in ranked if item.show_to_user]


def recommend_feeds(user: AbstractBaseUser, limit: int = 4) -> list[Feed]:
    """Suggest muted catalog feeds the user might re-enable."""
    muted_ids = FeedMute.objects.filter(user=user).values_list("feed_id", flat=True)
    qs = catalog_feeds().filter(id__in=muted_ids)

    enabled = set(enabled_feed_ids(user))
    user_categories = set(
        Feed.objects.filter(id__in=enabled).values_list("category", flat=True)
    )
    preferred = list(qs.filter(category__in=user_categories)[:limit])
    if len(preferred) < limit:
        preferred_ids = {f.id for f in preferred}
        preferred.extend(
            list(qs.exclude(id__in=preferred_ids)[: limit - len(preferred)])
        )
    return preferred
