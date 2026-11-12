"""Mixed Stories feed: unthreaded articles + collapsed story-thread cards."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from django.db.models import Count, Min
from django.utils import timezone

from news.models import Article, Feed, ImpactTier, StoryThread

EntryKind = Literal["article", "thread"]

HALF_LIFE_HOURS = 36.0
COVERAGE_BOOST_K = 0.45
DEFAULT_PAGE_SIZE = 21
FETCH_CAP = 400

TIER_WEIGHTS: dict[str, float] = {
    ImpactTier.COMMERCIAL: 0.15,
    ImpactTier.EPHEMERAL: 0.4,
    "": 0.35,
    ImpactTier.NOTABLE: 1.0,
    ImpactTier.MAJOR: 2.5,
}


@dataclass(frozen=True)
class StoryFeedEntry:
    kind: EntryKind
    sort_at: datetime
    score: float = 0.0
    article: Article | None = None
    thread: StoryThread | None = None
    article_count: int = 0
    lead_article: Article | None = None
    source_feeds: list[Feed] = field(default_factory=list)
    first_published_at: datetime | None = None
    span_label: str = ""
    image_url: str = ""
    is_new: bool = False

    @property
    def recency_at(self) -> datetime:
        """Watermark comparison: article publish time or thread last coverage."""
        return self.sort_at


@dataclass(frozen=True)
class StoriesFeedPage:
    entries: list[StoryFeedEntry]
    page: int
    page_size: int
    has_previous: bool
    has_next: bool
    since_active: bool


def format_thread_span(first: datetime, last: datetime) -> str:
    """Human label for how long a thread has been covered."""
    if last < first:
        first, last = last, first
    delta = last - first
    if delta < timedelta(minutes=30):
        return "same day"
    if delta < timedelta(hours=36):
        hours = max(1, int(round(delta.total_seconds() / 3600)))
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = max(1, int(round(delta.total_seconds() / 86400)))
    return f"{days} day{'s' if days != 1 else ''}"


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


def thread_impact_score(members: list[Article], *, now: datetime) -> float:
    """Max member score with a log-damped boost from additional coverage."""
    scores = [
        article_impact_score(member.impact_tier, member.published_at, now=now) for member in members
    ]
    if not scores:
        return 0.0
    base = max(scores)
    if base <= 0.0:
        return 0.0
    others = sum(scores) - base
    return base * (1.0 + COVERAGE_BOOST_K * math.log1p(others / base))


def build_stories_feed(
    feed_ids: list[int],
    *,
    limit: int = 40,
    now: datetime | None = None,
) -> list[StoryFeedEntry]:
    """Ranked mix of plain articles and multi-article thread cards.

    - Unthreaded articles in scope become article entries (near-duplicates hidden).
    - Threads with ≥1 in-scope member become one thread entry each, with total
      member count and the newest in-scope article as the lead preview.
    - Sorted by impact×decay (threads get a damped coverage boost), then recency.
    """
    ranked = _build_ranked_entries(feed_ids, fetch_limit=max(limit * 4, 80), now=now)
    return ranked[:limit]


def build_stories_feed_page(
    feed_ids: list[int],
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    since: datetime | None = None,
    now: datetime | None = None,
) -> StoriesFeedPage:
    """Ranked feed with optional new/earlier partition and has-next pagination.

    Does not compute a total page count — the ranked window grows over time and
    a precise "page X of Y" would be both costly and misleading.
    """
    safe_page = max(1, page)
    safe_size = max(1, page_size)
    fetch_limit = min(max(safe_page * safe_size * 5, 100), FETCH_CAP)
    ranked = _build_ranked_entries(feed_ids, fetch_limit=fetch_limit, now=now)

    if since is not None:
        new_entries = [_with_is_new(entry, True) for entry in ranked if entry.recency_at > since]
        earlier_entries = [
            _with_is_new(entry, False) for entry in ranked if entry.recency_at <= since
        ]
        ordered = new_entries + earlier_entries
        since_active = True
    else:
        ordered = [_with_is_new(entry, False) for entry in ranked]
        since_active = False

    start = (safe_page - 1) * safe_size
    window = ordered[start : start + safe_size + 1]
    has_next = len(window) > safe_size
    entries = window[:safe_size]
    # Past the end of the window: show an empty page rather than inventing a total.
    if not entries and safe_page > 1:
        return StoriesFeedPage(
            entries=[],
            page=safe_page,
            page_size=safe_size,
            has_previous=True,
            has_next=False,
            since_active=since_active,
        )

    return StoriesFeedPage(
        entries=entries,
        page=safe_page,
        page_size=safe_size,
        has_previous=safe_page > 1,
        has_next=has_next,
        since_active=since_active,
    )


def _with_is_new(entry: StoryFeedEntry, is_new: bool) -> StoryFeedEntry:
    return StoryFeedEntry(
        kind=entry.kind,
        sort_at=entry.sort_at,
        score=entry.score,
        article=entry.article,
        thread=entry.thread,
        article_count=entry.article_count,
        lead_article=entry.lead_article,
        source_feeds=entry.source_feeds,
        first_published_at=entry.first_published_at,
        span_label=entry.span_label,
        image_url=entry.image_url,
        is_new=is_new,
    )


def _first_member_image_url(members: list[Article]) -> str:
    """Newest-first member image; empty when no thread member has media."""
    for member in members:
        if member.image_url:
            return member.image_url
    return ""


def _build_ranked_entries(
    feed_ids: list[int],
    *,
    fetch_limit: int,
    now: datetime | None = None,
) -> list[StoryFeedEntry]:
    if not feed_ids:
        return []

    now = now or timezone.now()
    capped = min(max(fetch_limit, 1), FETCH_CAP)
    scoped = (
        Article.objects.filter(feed_id__in=feed_ids)
        .select_related("feed", "story_thread")
        .order_by("-published_at")[:capped]
    )
    articles = list(scoped)

    plain: list[StoryFeedEntry] = []
    thread_leads: dict[int, Article] = {}
    for article in articles:
        if article.near_duplicate_of_id is not None:
            continue
        thread_id = article.story_thread_id
        if thread_id is None:
            plain.append(
                StoryFeedEntry(
                    kind="article",
                    sort_at=article.published_at,
                    score=article_impact_score(
                        article.impact_tier,
                        article.published_at,
                        now=now,
                    ),
                    article=article,
                    image_url=article.image_url or "",
                )
            )
            continue
        # First seen is newest (queryset ordered by -published_at).
        if thread_id not in thread_leads:
            thread_leads[thread_id] = article

    if not thread_leads:
        return _sort_by_score(plain)

    threads = {
        t.id: t
        for t in StoryThread.objects.filter(id__in=thread_leads.keys()).annotate(
            member_count=Count("articles"),
            first_published_at=Min("articles__published_at"),
        )
    }

    members_by_thread: dict[int, list[Article]] = {tid: [] for tid in thread_leads}
    for member in (
        Article.objects.filter(story_thread_id__in=thread_leads.keys())
        .select_related("feed")
        .order_by("-published_at")
    ):
        tid = member.story_thread_id
        if tid is None:
            continue
        members_by_thread[tid].append(member)

    thread_entries: list[StoryFeedEntry] = []
    for thread_id, lead in thread_leads.items():
        thread = threads.get(thread_id)
        if thread is None:
            continue
        count = int(getattr(thread, "member_count", 0) or 0)
        members = members_by_thread.get(thread_id, [])
        if count < 2:
            # Singleton threads should be dissolved; treat lead as a plain article.
            plain.append(
                StoryFeedEntry(
                    kind="article",
                    sort_at=lead.published_at,
                    score=article_impact_score(
                        lead.impact_tier,
                        lead.published_at,
                        now=now,
                    ),
                    article=lead,
                    image_url=lead.image_url or "",
                )
            )
            continue

        first_published = getattr(thread, "first_published_at", None) or lead.published_at
        source_feeds = _unique_feeds(members, lead_feed=lead.feed)
        thread_entries.append(
            StoryFeedEntry(
                kind="thread",
                sort_at=thread.last_published_at,
                score=thread_impact_score(members, now=now),
                thread=thread,
                article_count=count,
                lead_article=lead,
                source_feeds=source_feeds,
                first_published_at=first_published,
                span_label=format_thread_span(first_published, thread.last_published_at),
                image_url=_first_member_image_url(members),
            )
        )

    return _sort_by_score(plain + thread_entries)


def _sort_by_score(entries: list[StoryFeedEntry]) -> list[StoryFeedEntry]:
    return sorted(entries, key=lambda e: (e.score, e.sort_at), reverse=True)


def _unique_feeds(members: list[Article], *, lead_feed: Feed) -> list[Feed]:
    """Lead feed first, then other sources in newest-member order."""
    ordered: list[Feed] = [lead_feed]
    seen = {lead_feed.id}
    for article in members:
        feed = article.feed
        if feed.id in seen:
            continue
        seen.add(feed.id)
        ordered.append(feed)
    return ordered


def thread_visible_in_scope(thread_id: int, feed_ids: list[int]) -> StoryThread | None:
    """Return the thread if it has ≥1 member in feed scope; else None."""
    if not feed_ids:
        return None
    return (
        StoryThread.objects.filter(
            pk=thread_id,
            articles__feed_id__in=feed_ids,
        )
        .annotate(member_count=Count("articles"))
        .distinct()
        .first()
    )


def thread_timeline_articles(thread: StoryThread) -> list[Article]:
    """All thread members newest-first (story thread page)."""
    return list(
        Article.objects.filter(story_thread=thread).select_related("feed").order_by("-published_at")
    )
