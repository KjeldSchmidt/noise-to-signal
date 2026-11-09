"""Thin client for the Django /api/internal/* routes."""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from n2s_api import (
    ArticleUpsert,
    ArticleUpsertResponse,
    Feed,
    FeedItem,
    FeedItemIngestRequest,
    FeedItemIngestResponse,
    FeedListResponse,
    GeocodePlace,
    GeocodeSearchRequest,
    GeocodeSearchResponse,
    ThemeDTO,
    ThemeListResponse,
)

DEFAULT_CHUNK_SIZE = 200


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _base_and_token(
    base_url: str | None,
    token: str | None,
) -> tuple[str, str]:
    base = (base_url or os.environ.get("WEB_API_BASE_URL", "")).rstrip("/")
    auth = token or os.environ.get("INTERNAL_API_TOKEN", "")
    if not base:
        raise ValueError("WEB_API_BASE_URL is required")
    if not auth:
        raise ValueError("INTERNAL_API_TOKEN is required")
    return base, auth


def list_feeds(
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> list[Feed]:
    """GET /api/internal/feeds/ with the shared INTERNAL_API_TOKEN."""
    base, auth = _base_and_token(base_url, token)
    request = urllib.request.Request(
        f"{base}/api/internal/feeds/",
        headers=_auth_headers(auth),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"list_feeds failed ({exc.code}): {body}") from exc

    return list(FeedListResponse.model_validate_json(raw).feeds)


def list_themes(
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> list[ThemeDTO]:
    """GET /api/internal/themes/ — active theme allowlist."""
    base, auth = _base_and_token(base_url, token)
    request = urllib.request.Request(
        f"{base}/api/internal/themes/",
        headers=_auth_headers(auth),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"list_themes failed ({exc.code}): {body}") from exc
    return list(ThemeListResponse.model_validate_json(raw).themes)


def geocode_search(
    query: str,
    *,
    limit: int = 5,
    lang: str = "en",
    scope_hint: str = "",
    base_url: str | None = None,
    token: str | None = None,
) -> list[GeocodePlace]:
    """POST /api/internal/geocode/search/ — Nominatim hierarchy + coords."""
    base, auth = _base_and_token(base_url, token)
    body = (
        GeocodeSearchRequest(
            q=query, limit=limit, lang=lang, scope_hint=scope_hint
        )
        .model_dump_json()
        .encode("utf-8")
    )
    request = urllib.request.Request(
        f"{base}/api/internal/geocode/search/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = GeocodeSearchResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"geocode_search failed ({exc.code}): {err}") from exc
    return list(payload.results)


def ingest_feed_items(
    items: list[FeedItem],
    *,
    base_url: str | None = None,
    token: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> FeedItemIngestResponse:
    """POST /api/internal/feed-items/ in chunks; sums accepted/skipped/enqueued."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    base, auth = _base_and_token(base_url, token)
    totals = FeedItemIngestResponse(accepted=0, skipped_existing=0, enqueued=0)
    if not items:
        return totals

    for offset in range(0, len(items), chunk_size):
        chunk = items[offset : offset + chunk_size]
        body = FeedItemIngestRequest(items=chunk).model_dump_json().encode("utf-8")
        request = urllib.request.Request(
            f"{base}/api/internal/feed-items/",
            data=body,
            headers=_auth_headers(auth),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                part = FeedItemIngestResponse.model_validate_json(response.read())
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ingest_feed_items failed ({exc.code}): {err_body}"
            ) from exc

        totals = FeedItemIngestResponse(
            accepted=totals.accepted + part.accepted,
            skipped_existing=totals.skipped_existing + part.skipped_existing,
            enqueued=totals.enqueued + part.enqueued,
        )
    return totals


def upsert_article(
    article: ArticleUpsert,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> ArticleUpsertResponse:
    """POST /api/internal/articles/ — idempotent article upsert."""
    base, auth = _base_and_token(base_url, token)
    body = article.model_dump_json().encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/internal/articles/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return ArticleUpsertResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upsert_article failed ({exc.code}): {err}") from exc
