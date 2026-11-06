"""JSON API for trusted internal callers (Lambdas)."""

from __future__ import annotations

from datetime import datetime, timezone

from django.http import HttpRequest, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from n2s_api import (
    ArticleUpsert,
    ArticleUpsertResponse,
    Feed as FeedDTO,
    FeedItemIngestRequest,
    FeedItemIngestResponse,
    FeedListResponse,
)
from pydantic import ValidationError

from news.internal_auth import require_internal_token
from news.models import Article, Feed
from news.sqs import enqueue_feed_items


@csrf_exempt
@require_GET
@require_internal_token
def list_feeds(request: HttpRequest) -> JsonResponse:
    """Return every RSS feed row (active and inactive) for ingestion workers."""
    payload = FeedListResponse(
        feeds=[
            FeedDTO(
                id=feed.id,
                title=feed.title,
                url=feed.url,
                site_url=feed.site_url,
                description=feed.description,
                category=feed.category,
                kind=feed.kind,
                owner_id=feed.owner_id,
                is_active=feed.is_active,
            )
            for feed in Feed.objects.order_by("id")
        ]
    )
    return JsonResponse(payload.model_dump())


@csrf_exempt
@require_POST
@require_internal_token
def ingest_feed_items(request: HttpRequest) -> JsonResponse:
    """Dedup FeedItems against Article(feed, url); enqueue only new ones to SQS."""
    try:
        batch = FeedItemIngestRequest.model_validate_json(
            request.body.decode("utf-8") or "{}"
        )
    except ValidationError as exc:
        return JsonResponse({"error": "invalid payload", "detail": exc.errors()}, status=400)

    items = list(batch.items)
    if not items:
        return JsonResponse(
            FeedItemIngestResponse(
                accepted=0, skipped_existing=0, enqueued=0
            ).model_dump()
        )

    for item in items:
        if not item.link or not item.feed_id:
            return JsonResponse({"error": "feed_id and link are required"}, status=400)

    feed_ids = {item.feed_id for item in items}
    existing_feeds = set(
        Feed.objects.filter(id__in=feed_ids).values_list("id", flat=True)
    )
    unknown = feed_ids - existing_feeds
    if unknown:
        return JsonResponse(
            {"error": f"unknown feed_id(s): {sorted(unknown)}"},
            status=400,
        )

    urls = [item.link for item in items]
    existing_keys = {
        (feed_id, url)
        for feed_id, url in Article.objects.filter(
            feed_id__in=feed_ids, url__in=urls
        ).values_list("feed_id", "url")
    }

    new_items = [item for item in items if (item.feed_id, item.link) not in existing_keys]
    skipped = len(items) - len(new_items)
    enqueued = enqueue_feed_items(new_items)

    return JsonResponse(
        FeedItemIngestResponse(
            accepted=len(new_items),
            skipped_existing=skipped,
            enqueued=enqueued,
        ).model_dump()
    )


def _parse_published_at(value: str) -> datetime:
    parsed = parse_datetime(value) if value else None
    if parsed is None:
        return datetime.now(timezone.utc)
    return parsed


@csrf_exempt
@require_POST
@require_internal_token
def upsert_article(request: HttpRequest) -> JsonResponse:
    """Idempotent Article create/update used by news_parser."""
    try:
        dto = ArticleUpsert.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse({"error": "invalid article", "detail": exc.errors()}, status=400)

    if not dto.url:
        return JsonResponse({"error": "url is required"}, status=400)
    if not Feed.objects.filter(id=dto.feed_id).exists():
        return JsonResponse({"error": f"unknown feed_id: {dto.feed_id}"}, status=400)

    defaults = {
        "title": dto.title[:300],
        "summary": dto.summary,
        "published_at": _parse_published_at(dto.published_at),
    }
    if dto.image_url:
        defaults["image_url"] = dto.image_url[:1000]
    article, created = Article.objects.update_or_create(
        feed_id=dto.feed_id,
        url=dto.url,
        defaults=defaults,
    )
    return JsonResponse(
        ArticleUpsertResponse(created=created, article_id=article.id).model_dump()
    )
