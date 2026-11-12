"""JSON API for trusted internal callers (Lambdas)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from django.http import HttpRequest, JsonResponse
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from n2s_api import (
    ArticleUpsert,
    ArticleUpsertResponse,
    FeedItemIngestRequest,
    FeedItemIngestResponse,
    FeedListResponse,
    GeocodePlace,
    GeocodeSearchRequest,
    GeocodeSearchResponse,
    ThemeDTO,
    ThemeListResponse,
)
from n2s_api import (
    Feed as FeedDTO,
)
from pydantic import ValidationError

from news.internal_auth import require_internal_token
from news.models import Article, EnrichmentStatus, Feed, GeoLevel, Theme
from news.services.feeds import feed_should_poll, feeds_for_list_api
from news.services.geocode import search_places
from news.services.themes import record_theme_suggestions
from news.services.threading import assign_story_thread
from news.sqs import enqueue_feed_items


def _validation_detail(exc: ValidationError) -> list:
    return json.loads(exc.json())


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
                language=feed.language or "en",
                should_poll=feed_should_poll(
                    kind=feed.kind,
                    is_active=feed.is_active,
                    subscription_count=int(getattr(feed, "subscription_count", 0) or 0),
                ),
            )
            for feed in feeds_for_list_api()
        ]
    )
    return JsonResponse(payload.model_dump())


@csrf_exempt
@require_GET
@require_internal_token
def list_themes(request: HttpRequest) -> JsonResponse:
    """Active theme allowlist for news_parser enrichment prompts."""
    payload = ThemeListResponse(
        themes=[
            ThemeDTO(slug=t.slug, label=t.label)
            for t in Theme.objects.filter(is_active=True).order_by("sort_order", "slug")
        ]
    )
    return JsonResponse(payload.model_dump())


@csrf_exempt
@require_POST
@require_internal_token
def geocode_search(request: HttpRequest) -> JsonResponse:
    """Forward-geocode for workers (Nominatim hierarchy + coords)."""
    try:
        dto = GeocodeSearchRequest.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid geocode request", "detail": _validation_detail(exc)},
            status=400,
        )
    hits = search_places(
        dto.q,
        limit=dto.limit,
        lang=dto.lang or "en",
        scope_hint=dto.scope_hint or None,
    )
    payload = GeocodeSearchResponse(
        results=[
            GeocodePlace(
                label=h["label"],
                latitude=h["latitude"],
                longitude=h["longitude"],
                country_code=h.get("country_code") or "",
                admin1=h.get("admin1") or "",
                locality=h.get("locality") or "",
                geo_level=h.get("geo_level") or GeoLevel.LOCALITY,
                osm_class=h.get("osm_class") or "",
                osm_type=h.get("osm_type") or "",
                importance=h.get("importance"),
            )
            for h in hits
        ]
    )
    return JsonResponse(payload.model_dump())


@csrf_exempt
@require_POST
@require_internal_token
def ingest_feed_items(request: HttpRequest) -> JsonResponse:
    """Dedup FeedItems against Article(feed, url); enqueue only new ones to SQS."""
    try:
        batch = FeedItemIngestRequest.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid payload", "detail": _validation_detail(exc)},
            status=400,
        )

    items = list(batch.items)
    if not items:
        return JsonResponse(
            FeedItemIngestResponse(accepted=0, skipped_existing=0, enqueued=0).model_dump()
        )

    for item in items:
        if not item.link or not item.feed_id:
            return JsonResponse({"error": "feed_id and link are required"}, status=400)

    feed_ids = {item.feed_id for item in items}
    existing_feeds = set(Feed.objects.filter(id__in=feed_ids).values_list("id", flat=True))
    unknown = feed_ids - existing_feeds
    if unknown:
        return JsonResponse(
            {"error": f"unknown feed_id(s): {sorted(unknown)}"},
            status=400,
        )

    urls = [item.link for item in items]
    existing_keys = {
        (feed_id, url)
        for feed_id, url in Article.objects.filter(feed_id__in=feed_ids, url__in=urls).values_list(
            "feed_id", "url"
        )
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
        return datetime.now(UTC)
    return parsed


@csrf_exempt
@require_POST
@require_internal_token
def upsert_article(request: HttpRequest) -> JsonResponse:
    """Idempotent Article create/update used by news_parser."""
    try:
        dto = ArticleUpsert.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid article", "detail": _validation_detail(exc)},
            status=400,
        )

    if not dto.url:
        return JsonResponse({"error": "url is required"}, status=400)
    if not Feed.objects.filter(id=dto.feed_id).exists():
        return JsonResponse({"error": f"unknown feed_id: {dto.feed_id}"}, status=400)

    defaults = {
        "title": dto.title[:300],
        "summary": dto.summary,
        "published_at": _parse_published_at(dto.published_at),
        "geo_level": dto.geo_level or GeoLevel.GLOBAL,
        "place_label": (dto.place_label or "")[:200],
        "country_code": (dto.country_code or "")[:2],
        "admin1": (dto.admin1 or "")[:120],
        "locality": (dto.locality or "")[:120],
        "latitude": dto.latitude,
        "longitude": dto.longitude,
        "geo_confidence": dto.geo_confidence,
        "story_label": (dto.story_label or "")[:120],
        "impact_tier": (dto.impact_tier or "")[:20],
        "impact_rationale": (dto.impact_rationale or "")[:160],
    }
    if dto.image_url:
        defaults["image_url"] = dto.image_url[:1000]
    if dto.embedding is not None:
        defaults["embedding"] = dto.embedding
        defaults["embedding_model"] = (dto.embedding_model or "")[:80]
        defaults["embedded_at"] = django_timezone.now()
    status = (dto.enrichment_status or "").strip().lower()
    if status in {EnrichmentStatus.OK, EnrichmentStatus.DEGRADED}:
        defaults["enrichment_status"] = status
        defaults["extract_model"] = (dto.extract_model or "")[:120]
        defaults["enriched_at"] = django_timezone.now()
    article, created = Article.objects.update_or_create(
        feed_id=dto.feed_id,
        url=dto.url,
        defaults=defaults,
    )
    if dto.theme_slugs:
        themes = Theme.objects.filter(is_active=True, slug__in=dto.theme_slugs)
        article.themes.set(themes)
    else:
        article.themes.clear()
    if dto.suggested_themes:
        record_theme_suggestions(
            list(dto.suggested_themes),
            example_title=article.title,
        )
    if dto.embedding is not None:
        article = assign_story_thread(article)
    return JsonResponse(
        ArticleUpsertResponse(
            created=created,
            article_id=article.id,
            story_thread_id=article.story_thread_id,
        ).model_dump()
    )
