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
    ArticleEmbeddingExportResponse,
    ArticleEmbeddingExportRow,
    ArticleSearchRequest,
    ArticleSearchResponse,
    ArticleUpsert,
    ArticleUpsertResponse,
    BriefCompleteRequest,
    BriefCompleteResponse,
    FeedItemIngestRequest,
    FeedItemIngestResponse,
    FeedListResponse,
    FeedPollStateRequest,
    FeedPollStateResponse,
    GeocodePlace,
    GeocodeSearchRequest,
    GeocodeSearchResponse,
    StoryThreadMemberDTO,
    StoryThreadSummaryContextResponse,
    StoryThreadSummaryUpdateRequest,
    StoryThreadSummaryUpdateResponse,
    ThemeDTO,
    ThemeListResponse,
    encode_embedding_f32_b64,
)
from n2s_api import (
    Feed as FeedDTO,
)
from pydantic import ValidationError

from news.internal_auth import require_internal_token
from news.models import (
    Article,
    EnrichmentStatus,
    Feed,
    GeoLevel,
    StoryThread,
    Theme,
    UserBrief,
    UserBriefItem,
)
from news.services.article_search import search_articles_by_user_id
from news.services.brief_context import build_brief_user_context
from news.services.feeds import feed_should_poll, feeds_for_list_api
from news.services.geocode import search_places
from news.services.themes import record_theme_suggestions
from news.services.thread_summary import maybe_invoke_thread_summary
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
                http_etag=feed.http_etag or "",
                http_last_modified=feed.http_last_modified or "",
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


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_GET  # ty: ignore[invalid-argument-type]
@require_internal_token
def export_article_embeddings(request: HttpRequest) -> JsonResponse:
    """Paginated export of stored embeddings + theme slugs for theme_analysis."""
    try:
        cursor_raw = (request.GET.get("cursor") or "").strip()
        cursor = int(cursor_raw) if cursor_raw else 0
        if cursor < 0:
            raise ValueError("cursor must be >= 0")
        limit_raw = (request.GET.get("limit") or "200").strip()
        limit = int(limit_raw)
        if limit < 1 or limit > 500:
            raise ValueError("limit must be 1..500")
    except ValueError as exc:
        return JsonResponse({"error": "invalid query", "detail": str(exc)}, status=400)

    qs = (
        Article.objects.filter(embedding__isnull=False)
        .filter(id__gt=cursor)
        .order_by("id")
        .prefetch_related("themes")[: limit + 1]
    )
    rows = list(qs)
    has_more = len(rows) > limit
    page = rows[:limit]
    theme_order = {
        slug: idx
        for idx, slug in enumerate(
            Theme.objects.filter(is_active=True)
            .order_by("sort_order", "slug")
            .values_list("slug", flat=True)
        )
    }
    articles: list[ArticleEmbeddingExportRow] = []
    for article in page:
        emb = article.embedding
        if emb is None:
            continue
        values = [float(x) for x in list(emb)]
        if len(values) != 1024:
            continue
        slugs = sorted(
            (t.slug for t in article.themes.all() if t.is_active),
            key=lambda s: (theme_order.get(s, 10_000), s),
        )
        articles.append(
            ArticleEmbeddingExportRow(
                id=article.id,
                title=article.title,
                theme_slugs=slugs,
                embedding_b64=encode_embedding_f32_b64(values),
            )
        )
    next_cursor = page[-1].id if has_more and page else None
    return JsonResponse(
        ArticleEmbeddingExportResponse(articles=articles, next_cursor=next_cursor).model_dump()
    )


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_POST  # ty: ignore[invalid-argument-type]
@require_internal_token
def search_articles(request: HttpRequest) -> JsonResponse:
    """Title + embedding article search scoped to a user's enabled feeds."""
    try:
        dto = ArticleSearchRequest.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid search request", "detail": _validation_detail(exc)},
            status=400,
        )

    results = search_articles_by_user_id(
        user_id=dto.user_id,
        query=dto.query,
        embedding=dto.embedding,
        limit=dto.limit,
        exclude_article_ids=list(dto.exclude_article_ids),
    )
    if results is None:
        return JsonResponse({"error": f"unknown user_id: {dto.user_id}"}, status=404)
    return JsonResponse(ArticleSearchResponse(results=results).model_dump())


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
        before_thread_id = article.story_thread_id
        article = assign_story_thread(article)
        if article.story_thread_id and article.story_thread_id != before_thread_id:
            maybe_invoke_thread_summary(article.story_thread_id)
    return JsonResponse(
        ArticleUpsertResponse(
            created=created,
            article_id=article.id,
            story_thread_id=article.story_thread_id,
        ).model_dump()
    )


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_GET  # ty: ignore[invalid-argument-type]
@require_internal_token
def brief_user_context(request: HttpRequest, user_id: int) -> JsonResponse:
    """User settings + Stories-scored candidates for brief_builder."""
    payload = build_brief_user_context(user_id)
    return JsonResponse(payload.model_dump())


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_POST  # ty: ignore[invalid-argument-type]
@require_internal_token
def complete_brief(request: HttpRequest) -> JsonResponse:
    """Mark a pending UserBrief ready/failed and replace its items."""
    try:
        dto = BriefCompleteRequest.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid payload", "detail": _validation_detail(exc)},
            status=400,
        )

    try:
        brief = UserBrief.objects.get(pk=dto.brief_id, user_id=dto.user_id)
    except UserBrief.DoesNotExist:
        return JsonResponse({"error": "brief not found"}, status=404)

    if dto.status == "failed":
        brief.status = UserBrief.Status.FAILED
        brief.error = (dto.error or "brief build failed")[:2000]
        brief.ready_at = None
        brief.save(update_fields=["status", "error", "ready_at", "updated_at"])
        return JsonResponse(
            BriefCompleteResponse(brief_id=brief.id, status="failed", item_count=0).model_dump()
        )

    article_ids = [item.article_id for item in dto.items if item.article_id is not None]
    thread_ids = [item.story_thread_id for item in dto.items if item.story_thread_id is not None]
    if article_ids:
        existing_articles = set(
            Article.objects.filter(id__in=article_ids).values_list("id", flat=True)
        )
        missing_articles = sorted(set(article_ids) - existing_articles)
        if missing_articles:
            return JsonResponse(
                {"error": f"unknown article_id(s): {missing_articles}"},
                status=400,
            )
    if thread_ids:
        existing_threads = set(
            StoryThread.objects.filter(id__in=thread_ids).values_list("id", flat=True)
        )
        missing_threads = sorted(set(thread_ids) - existing_threads)
        if missing_threads:
            return JsonResponse(
                {"error": f"unknown story_thread_id(s): {missing_threads}"},
                status=400,
            )

    UserBriefItem.objects.filter(brief=brief).delete()
    UserBriefItem.objects.bulk_create(
        [
            UserBriefItem(
                brief=brief,
                article_id=item.article_id if item.kind == "article" else None,
                story_thread_id=item.story_thread_id if item.kind == "thread" else None,
                rank=item.rank,
                score=item.score,
                reason=(item.reason or "")[:2000],
            )
            for item in dto.items
        ]
    )
    brief.status = UserBrief.Status.READY
    brief.ready_at = django_timezone.now()
    brief.error = ""
    brief.save(update_fields=["status", "ready_at", "error", "updated_at"])
    return JsonResponse(
        BriefCompleteResponse(
            brief_id=brief.id,
            status="ready",
            item_count=len(dto.items),
        ).model_dump()
    )


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_GET  # ty: ignore[invalid-argument-type]
@require_internal_token
def story_thread_summary_context(request: HttpRequest, thread_id: int) -> JsonResponse:
    """Member titles/summaries for the story_summarizer worker."""
    try:
        thread = StoryThread.objects.get(pk=thread_id)
    except StoryThread.DoesNotExist:
        return JsonResponse({"error": "story thread not found"}, status=404)

    articles = list(
        Article.objects.filter(story_thread=thread)
        .select_related("feed")
        .order_by("-published_at")[:20]
    )
    payload = StoryThreadSummaryContextResponse(
        story_thread_id=thread.id,
        label=thread.label or "",
        articles=[
            StoryThreadMemberDTO(
                title=article.title,
                summary=(article.summary or "")[:800],
                source=article.feed.title if article.feed_id else "",
                published_at=article.published_at.isoformat(),
            )
            for article in articles
        ],
    )
    return JsonResponse(payload.model_dump())


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_POST  # ty: ignore[invalid-argument-type]
@require_internal_token
def update_story_thread_summary(request: HttpRequest) -> JsonResponse:
    """Persist a non-personal AI digest on a StoryThread."""
    try:
        dto = StoryThreadSummaryUpdateRequest.model_validate_json(
            request.body.decode("utf-8") or "{}"
        )
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid payload", "detail": _validation_detail(exc)},
            status=400,
        )

    summary = (dto.summary or "").strip()
    if not summary:
        return JsonResponse({"error": "summary is required"}, status=400)

    try:
        thread = StoryThread.objects.get(pk=dto.story_thread_id)
    except StoryThread.DoesNotExist:
        return JsonResponse({"error": "story thread not found"}, status=404)

    now = django_timezone.now()
    thread.summary = summary[:8000]
    thread.summarized_at = now
    thread.save(update_fields=["summary", "summarized_at", "updated_at"])
    return JsonResponse(
        StoryThreadSummaryUpdateResponse(
            story_thread_id=thread.id,
            summarized_at=now.isoformat(),
            summary_chars=len(thread.summary),
        ).model_dump()
    )


@csrf_exempt  # ty: ignore[invalid-argument-type]
@require_POST  # ty: ignore[invalid-argument-type]
@require_internal_token
def update_feed_poll_state(request: HttpRequest) -> JsonResponse:
    """Persist RSS conditional-GET validators (ETag / Last-Modified) after a poll."""
    try:
        batch = FeedPollStateRequest.model_validate_json(request.body.decode("utf-8") or "{}")
    except ValidationError as exc:
        return JsonResponse(
            {"error": "invalid payload", "detail": _validation_detail(exc)},
            status=400,
        )

    updates = list(batch.updates)
    if not updates:
        return JsonResponse(FeedPollStateResponse(updated=0).model_dump())

    feed_ids = {row.feed_id for row in updates}
    feeds_by_id = {feed.id: feed for feed in Feed.objects.filter(id__in=feed_ids)}
    unknown = feed_ids - set(feeds_by_id)
    if unknown:
        return JsonResponse(
            {"error": f"unknown feed_id(s): {sorted(unknown)}"},
            status=400,
        )

    updated = 0
    for row in updates:
        feed = feeds_by_id[row.feed_id]
        etag = (row.http_etag or "")[:255]
        modified = (row.http_last_modified or "")[:64]
        if feed.http_etag == etag and feed.http_last_modified == modified:
            continue
        feed.http_etag = etag
        feed.http_last_modified = modified
        feed.save(update_fields=["http_etag", "http_last_modified", "updated_at"])
        updated += 1

    return JsonResponse(FeedPollStateResponse(updated=updated).model_dump())
