"""Thin client for the Django /api/internal/* routes."""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from n2s_api import (
    ArticleEmbeddingExportResponse,
    ArticleEmbeddingExportRow,
    ArticleSearchRequest,
    ArticleSearchResponse,
    ArticleUpsert,
    ArticleUpsertResponse,
    BriefCompleteRequest,
    BriefCompleteResponse,
    BriefUserContextResponse,
    ContextChunk,
    Feed,
    FeedItem,
    FeedItemIngestRequest,
    FeedItemIngestResponse,
    FeedListResponse,
    FeedPollStateRequest,
    FeedPollStateResponse,
    FeedPollStateUpdate,
    GeocodePlace,
    GeocodeSearchRequest,
    GeocodeSearchResponse,
    StoryThreadSummaryContextResponse,
    StoryThreadSummaryUpdateRequest,
    StoryThreadSummaryUpdateResponse,
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


def update_feed_poll_state(
    updates: list[FeedPollStateUpdate],
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> FeedPollStateResponse:
    """POST /api/internal/feeds/poll-state/ — persist ETag / Last-Modified validators."""
    base, auth = _base_and_token(base_url, token)
    body = FeedPollStateRequest(updates=updates).model_dump_json().encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/internal/feeds/poll-state/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return FeedPollStateResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"update_feed_poll_state failed ({exc.code}): {err}") from exc


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
        GeocodeSearchRequest(q=query, limit=limit, lang=lang, scope_hint=scope_hint)
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
            raise RuntimeError(f"ingest_feed_items failed ({exc.code}): {err_body}") from exc

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


def search_articles(
    req: ArticleSearchRequest,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> list[ContextChunk]:
    """POST /api/internal/articles/search/ — title + embedding article search."""
    base, auth = _base_and_token(base_url, token)
    body = req.model_dump_json().encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/internal/articles/search/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = ArticleSearchResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"search_articles failed ({exc.code}): {err}") from exc
    return list(payload.results)


def export_article_embeddings(
    *,
    cursor: int = 0,
    limit: int = 200,
    base_url: str | None = None,
    token: str | None = None,
) -> ArticleEmbeddingExportResponse:
    """GET /api/internal/articles/embeddings/ — keyset page of vectors + themes."""
    base, auth = _base_and_token(base_url, token)
    query = urllib.parse.urlencode({"cursor": cursor, "limit": limit})
    request = urllib.request.Request(
        f"{base}/api/internal/articles/embeddings/?{query}",
        headers=_auth_headers(auth),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return ArticleEmbeddingExportResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"export_article_embeddings failed ({exc.code}): {err}") from exc


def iter_article_embeddings(
    *,
    page_size: int = 200,
    base_url: str | None = None,
    token: str | None = None,
) -> list[ArticleEmbeddingExportRow]:
    """Fetch every embedded article page (caller should expect up to ~10k rows)."""
    out: list[ArticleEmbeddingExportRow] = []
    cursor = 0
    while True:
        page = export_article_embeddings(
            cursor=cursor,
            limit=page_size,
            base_url=base_url,
            token=token,
        )
        out.extend(page.articles)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return out


def get_brief_user_context(
    user_id: int,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> BriefUserContextResponse:
    """GET /api/internal/briefs/users/<id>/context/."""
    base, auth = _base_and_token(base_url, token)
    request = urllib.request.Request(
        f"{base}/api/internal/briefs/users/{user_id}/context/",
        headers=_auth_headers(auth),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return BriefUserContextResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"get_brief_user_context failed ({exc.code}): {err}") from exc


def complete_brief(
    req: BriefCompleteRequest,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> BriefCompleteResponse:
    """POST /api/internal/briefs/complete/."""
    base, auth = _base_and_token(base_url, token)
    body = req.model_dump_json().encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/internal/briefs/complete/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return BriefCompleteResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"complete_brief failed ({exc.code}): {err}") from exc


def get_story_thread_summary_context(
    story_thread_id: int,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> StoryThreadSummaryContextResponse:
    """GET /api/internal/story-threads/<id>/summary-context/."""
    base, auth = _base_and_token(base_url, token)
    request = urllib.request.Request(
        f"{base}/api/internal/story-threads/{story_thread_id}/summary-context/",
        headers=_auth_headers(auth),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return StoryThreadSummaryContextResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"get_story_thread_summary_context failed ({exc.code}): {err}") from exc


def update_story_thread_summary(
    req: StoryThreadSummaryUpdateRequest,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> StoryThreadSummaryUpdateResponse:
    """POST /api/internal/story-threads/summary/."""
    base, auth = _base_and_token(base_url, token)
    body = req.model_dump_json().encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/internal/story-threads/summary/",
        data=body,
        headers=_auth_headers(auth),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return StoryThreadSummaryUpdateResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"update_story_thread_summary failed ({exc.code}): {err}") from exc
