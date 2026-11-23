"""Personalized brief freshness, kickoff, and interim Stories-style ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone

from news.models import Article, RelevanceFeedback, UserBrief, UserBriefItem
from news.services.feeds import enabled_feed_ids
from news.services.ranking import RankedItem
from news.services.stories_feed import build_stories_feed

BRIEF_TTL = timedelta(hours=6)
INTERIM_LIMIT = 12
CANDIDATE_LIMIT = 30

BriefPhase = Literal["caught_up", "ready", "personalizing", "failed", "empty"]


@dataclass(frozen=True)
class BriefPageState:
    phase: BriefPhase
    brief: UserBrief | None
    ranked: list[RankedItem]
    poll: bool
    kick: bool
    """True when the view should Event-invoke the brief builder for `brief`."""


def latest_brief(user: AbstractBaseUser) -> UserBrief | None:
    return (
        UserBrief.objects.filter(user=user)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=UserBriefItem.objects.select_related("article", "article__feed")
                .prefetch_related("article__themes")
                .order_by("rank"),
            )
        )
        .order_by("-created_at")
        .first()
    )


def brief_is_fresh(brief: UserBrief, *, now: datetime | None = None) -> bool:
    """True when a ready brief is still inside the 6h reuse window."""
    if brief.status != UserBrief.Status.READY or brief.ready_at is None:
        return False
    clock = now or timezone.now()
    return brief.ready_at >= clock - BRIEF_TTL


def ranked_from_brief(brief: UserBrief) -> list[RankedItem]:
    if not brief.pk:
        return []
    items = list(
        UserBriefItem.objects.filter(brief=brief)
        .select_related("article", "article__feed")
        .prefetch_related("article__themes")
        .order_by("rank")
    )
    return [
        RankedItem(
            article=item.article,
            score=round(float(item.score), 2),
            reason=item.reason or "Selected for your brief.",
            show_to_user=True,
        )
        for item in items
    ]


def interim_ranked_items(user: AbstractBaseUser, *, limit: int = INTERIM_LIMIT) -> list[RankedItem]:
    """Stories-style ranking as a stand-in while personalization runs."""
    feed_ids = enabled_feed_ids(user)
    if not feed_ids:
        return []
    judged = set(RelevanceFeedback.objects.filter(user=user).values_list("article_id", flat=True))
    entries = build_stories_feed(feed_ids, limit=limit * 2)
    ranked: list[RankedItem] = []
    for entry in entries:
        article: Article | None = None
        reason = "Top story while we personalize your brief."
        if entry.kind == "article" and entry.article is not None:
            article = entry.article
        elif entry.kind == "thread" and entry.lead_article is not None:
            article = entry.lead_article
            reason = "Active story thread while we personalize your brief."
        if article is None or article.id in judged:
            continue
        ranked.append(
            RankedItem(
                article=article,
                score=round(float(entry.score), 2),
                reason=reason,
                show_to_user=True,
            )
        )
        if len(ranked) >= limit:
            break
    if ranked:
        prefetch_related_objects([item.article for item in ranked], "themes")
    return ranked


def resolve_brief_page(user: AbstractBaseUser) -> BriefPageState:
    """Decide caught-up / personalizing / ready and whether to kick a new run."""
    feed_ids = enabled_feed_ids(user)
    if not feed_ids:
        return BriefPageState(phase="empty", brief=None, ranked=[], poll=False, kick=False)

    current = latest_brief(user)
    now = timezone.now()

    if (
        current is not None
        and current.status == UserBrief.Status.READY
        and brief_is_fresh(current, now=now)
    ):
        return BriefPageState(
            phase="caught_up",
            brief=current,
            ranked=ranked_from_brief(current),
            poll=False,
            kick=False,
        )

    if current is not None and current.status == UserBrief.Status.PENDING:
        return BriefPageState(
            phase="personalizing",
            brief=current,
            ranked=interim_ranked_items(user),
            poll=True,
            kick=False,
        )

    if (
        current is not None
        and current.status == UserBrief.Status.READY
        and not brief_is_fresh(current, now=now)
    ):
        brief = UserBrief.objects.create(user=user, status=UserBrief.Status.PENDING)
        return BriefPageState(
            phase="personalizing",
            brief=brief,
            ranked=ranked_from_brief(current),
            poll=True,
            kick=True,
        )

    # No brief, failed previous, or other — start a new pending run.
    stale_ranked = (
        ranked_from_brief(current)
        if current is not None and current.status == UserBrief.Status.READY
        else interim_ranked_items(user)
    )
    brief = UserBrief.objects.create(user=user, status=UserBrief.Status.PENDING)
    return BriefPageState(
        phase="personalizing",
        brief=brief,
        ranked=stale_ranked or interim_ranked_items(user),
        poll=True,
        kick=True,
    )
