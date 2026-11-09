"""news_parser — SQS-triggered enricher (embed + place/themes → Article upsert)."""

from __future__ import annotations

import logging
from typing import Any

from n2s_api import ArticleUpsert, FeedItem

from embed import EMBEDDING_MODEL_ID, build_embed_input, embed_text
from extract import extract_place_and_themes
from n2s_web_client import geocode_search, list_themes, upsert_article
from textutil import clean_text

logger = logging.getLogger(__name__)

_theme_slug_cache: list[str] | None = None


def _active_theme_slugs() -> list[str]:
    global _theme_slug_cache
    if _theme_slug_cache is None:
        _theme_slug_cache = [t.slug for t in list_themes()]
    return _theme_slug_cache


def _enrich_place_fields(
    *, title: str, summary: str
) -> dict[str, Any]:
    """Best-effort geo + themes; never raises (soft-fail to global)."""
    out: dict[str, Any] = {
        "geo_level": "global",
        "place_label": "",
        "country_code": "",
        "admin1": "",
        "locality": "",
        "latitude": None,
        "longitude": None,
        "geo_confidence": None,
        "theme_slugs": [],
    }
    try:
        extracted = extract_place_and_themes(
            title=title,
            summary=summary,
            theme_slugs=_active_theme_slugs(),
        )
    except Exception:
        logger.exception("Place/theme extraction failed; using global")
        return out

    out["theme_slugs"] = list(extracted.get("theme_slugs") or [])
    out["geo_confidence"] = extracted.get("geo_confidence")
    place_query = (extracted.get("place_query") or "").strip()
    scope = extracted.get("geo_scope") or "global"
    if not place_query or scope == "global":
        return out

    try:
        hits = geocode_search(place_query, limit=1, scope_hint=scope)
    except Exception:
        logger.exception("Geocode failed for %r; keeping global", place_query)
        return out
    if not hits:
        return out

    hit = hits[0]
    out.update(
        {
            "geo_level": hit.geo_level or "global",
            "place_label": hit.label or "",
            "country_code": hit.country_code or "",
            "admin1": hit.admin1 or "",
            "locality": hit.locality or "",
            "latitude": hit.latitude,
            "longitude": hit.longitude,
        }
    )
    return out


def enrich_feed_item(item: FeedItem) -> ArticleUpsert:
    """Normalize text, embed, and attach hierarchical place + allowlisted themes."""
    title = clean_text(item.title)[:300]
    summary = clean_text(item.description)
    embedding = embed_text(build_embed_input(title=title, summary=summary))
    place = _enrich_place_fields(title=title, summary=summary)
    return ArticleUpsert(
        feed_id=item.feed_id,
        url=item.link,
        title=title,
        summary=summary,
        published_at=item.published_at,
        image_url=item.thumbnail,
        embedding=embedding,
        embedding_model=EMBEDDING_MODEL_ID,
        geo_level=place["geo_level"],
        place_label=place["place_label"],
        country_code=place["country_code"],
        admin1=place["admin1"],
        locality=place["locality"],
        latitude=place["latitude"],
        longitude=place["longitude"],
        geo_confidence=place["geo_confidence"],
        theme_slugs=place["theme_slugs"],
    )


def process_feed_item(item: FeedItem) -> dict[str, Any]:
    article = enrich_feed_item(item)
    result = upsert_article(article)
    return {
        "feed_id": item.feed_id,
        "url": item.link,
        "created": result.created,
        "article_id": result.article_id,
        "story_thread_id": result.story_thread_id,
        "geo_level": article.geo_level,
        "theme_slugs": list(article.theme_slugs),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS event source mapping entrypoint."""
    records = event.get("Records") or []
    results: list[dict[str, Any]] = []
    batch_failures: list[dict[str, str]] = []

    for record in records:
        message_id = str(record.get("messageId") or "")
        try:
            item = FeedItem.model_validate_json(record.get("body") or "{}")
            if not item.link:
                raise ValueError("missing link")
            results.append(process_feed_item(item))
        except Exception:
            logger.exception("Failed to process SQS message %s", message_id)
            if message_id:
                batch_failures.append({"itemIdentifier": message_id})

    response: dict[str, Any] = {
        "ok": len(batch_failures) == 0,
        "processed": len(results),
        "results": results,
    }
    if batch_failures:
        response["batchItemFailures"] = batch_failures
    return response
