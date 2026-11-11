"""Mixed Stories feed: unthreaded articles + collapsed story-thread cards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from django.db.models import Count, Min

from news.models import Article, Feed, StoryThread

EntryKind = Literal["article", "thread"]


@dataclass(frozen=True)
class StoryFeedEntry:
    kind: EntryKind
    sort_at: datetime
    article: Article | None = None
    thread: StoryThread | None = None
    article_count: int = 0
    lead_article: Article | None = None
    source_feeds: list[Feed] = field(default_factory=list)
    first_published_at: datetime | None = None
    span_label: str = ""


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


def build_stories_feed(
    feed_ids: list[int],
    *,
    limit: int = 40,
) -> list[StoryFeedEntry]:
    """Chronological mix of plain articles and multi-article thread cards.

    - Unthreaded articles in scope become article entries (near-duplicates hidden).
    - Threads with ≥1 in-scope member become one thread entry each, with total
      member count and the newest in-scope article as the lead preview.
    """
    if not feed_ids:
        return []

    # Over-fetch so collapsing threaded members still fills the page.
    fetch_limit = max(limit * 4, 80)
    scoped = (
        Article.objects.filter(feed_id__in=feed_ids)
        .select_related("feed", "story_thread")
        .order_by("-published_at")[:fetch_limit]
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
                    article=article,
                )
            )
            continue
        # First seen is newest (queryset ordered by -published_at).
        if thread_id not in thread_leads:
            thread_leads[thread_id] = article

    if not thread_leads:
        plain.sort(key=lambda e: e.sort_at, reverse=True)
        return plain[:limit]

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
        if count < 2:
            # Singleton threads should be dissolved; treat lead as a plain article.
            plain.append(
                StoryFeedEntry(
                    kind="article",
                    sort_at=lead.published_at,
                    article=lead,
                )
            )
            continue

        first_published = getattr(thread, "first_published_at", None) or lead.published_at
        source_feeds = _unique_feeds(members_by_thread.get(thread_id, []), lead_feed=lead.feed)
        thread_entries.append(
            StoryFeedEntry(
                kind="thread",
                sort_at=thread.last_published_at,
                thread=thread,
                article_count=count,
                lead_article=lead,
                source_feeds=source_feeds,
                first_published_at=first_published,
                span_label=format_thread_span(first_published, thread.last_published_at),
            )
        )

    merged = plain + thread_entries
    merged.sort(key=lambda e: e.sort_at, reverse=True)
    return merged[:limit]


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
