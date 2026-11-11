"""Enqueue existing articles back onto the news_parser SQS queue."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone
from n2s_api import FeedItem

from news.models import Article
from news.sqs import enqueue_feed_items


def articles_for_requeue(
    *,
    all_articles: bool = False,
    unthreaded: bool = False,
    ids: list[int] | None = None,
    since_hours: int | None = None,
    enriched_before_hours: int | None = None,
) -> QuerySet[Article]:
    """Select articles for requeue.

    ``enriched_before_hours`` is a refinement (not a sole selector): keep rows that
    were never enriched or last enriched more than N hours ago — skips a recent
    test pass when widening the publish window.
    """
    qs = Article.objects.all().order_by("id")
    selected = False
    if all_articles:
        selected = True
    if unthreaded:
        qs = qs.filter(story_thread__isnull=True)
        selected = True
    if ids:
        qs = qs.filter(id__in=ids)
        selected = True
    if since_hours is not None:
        qs = qs.filter(published_at__gte=timezone.now() - timedelta(hours=since_hours))
        selected = True
    if not selected:
        raise ValueError("Select articles with all, unthreaded, ids, and/or since_hours")
    if enriched_before_hours is not None:
        cutoff = timezone.now() - timedelta(hours=enriched_before_hours)
        qs = qs.filter(Q(enriched_at__isnull=True) | Q(enriched_at__lt=cutoff))
    return qs.select_related("feed")


def requeue_articles(
    qs: QuerySet[Article],
    *,
    clear_threads: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    articles = list(qs)
    if dry_run:
        return {"count": len(articles), "cleared": 0, "enqueued": 0}

    cleared = 0
    if clear_threads and articles:
        cleared = Article.objects.filter(id__in=[a.id for a in articles]).update(
            story_thread_id=None,
            near_duplicate_of_id=None,
        )

    items: list[FeedItem] = []
    for article in articles:
        published = article.published_at.isoformat() if article.published_at else ""
        items.append(
            FeedItem(
                feed_id=article.feed_id,
                id=str(article.id),
                link=article.url,
                title=article.title,
                description=article.summary or "",
                published_at=published,
                thumbnail=article.image_url or "",
            )
        )
    enqueued = enqueue_feed_items(items)
    return {"count": len(articles), "cleared": cleared, "enqueued": enqueued}
