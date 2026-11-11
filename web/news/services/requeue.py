"""Enqueue existing articles back onto the news_parser SQS queue."""

from __future__ import annotations

from datetime import datetime

from django.db.models import QuerySet
from n2s_api import FeedItem

from news.models import Article
from news.sqs import enqueue_feed_items


def articles_for_requeue(
    *,
    all_articles: bool = False,
    unthreaded: bool = False,
    ids: list[int] | None = None,
    since: datetime | None = None,
) -> QuerySet[Article]:
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
    if since is not None:
        qs = qs.filter(published_at__gte=since)
        selected = True
    if not selected:
        raise ValueError("Select articles with all, unthreaded, ids, and/or since")
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
