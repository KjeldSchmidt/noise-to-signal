"""JSON API for trusted internal callers (Lambdas)."""

from __future__ import annotations

from dataclasses import asdict

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from n2s_api import Feed as FeedDTO, FeedListResponse

from news.internal_auth import require_internal_token
from news.models import Feed


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
    return JsonResponse(asdict(payload))
