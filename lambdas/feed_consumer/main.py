"""RSS feed consumer — Lambda handler + local runner."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import feedparser
from dotenv import load_dotenv
from n2s_api import FeedItem
from n2s_web_client import ingest_feed_items, list_feeds

logger = logging.getLogger(__name__)


def _entry_thumbnail(entry: Any) -> str:
    thumbs = getattr(entry, "media_thumbnail", None) or []
    if thumbs and isinstance(thumbs[0], dict):
        url = str(thumbs[0].get("url") or "")
        if url:
            return url
    for media in getattr(entry, "media_content", None) or []:
        if not isinstance(media, dict):
            continue
        if str(media.get("medium") or "") == "image" or str(media.get("type") or "").startswith(
            "image/"
        ):
            url = str(media.get("url") or "")
            if url:
                return url
    for enc in getattr(entry, "enclosures", None) or []:
        if not isinstance(enc, dict):
            continue
        if str(enc.get("type") or "").startswith("image/"):
            url = str(enc.get("href") or enc.get("url") or "")
            if url:
                return url
    return ""


def _entry_description(entry: Any) -> str:
    summary = getattr(entry, "summary", None)
    if summary:
        return str(summary)
    detail = getattr(entry, "summary_detail", None)
    if detail is not None and getattr(detail, "value", None):
        return str(detail.value)
    return ""


def _struct_to_datetime(value: Any) -> datetime | None:
    """Convert feedparser time.struct_time-like values to aware UTC datetimes."""
    if not value:
        return None
    try:
        return datetime(*value[:6], tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _entry_published_at(entry: Any) -> datetime:
    """Prefer RSS/Atom published, then updated/created; last resort ingest time."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = _struct_to_datetime(getattr(entry, attr, None))
        if parsed is not None:
            return parsed
    return datetime.now(UTC)


def collect_feed_items() -> list[FeedItem]:
    """Fetch feed list from the web API and parse each RSS URL."""
    items: list[FeedItem] = []
    feeds = list_feeds()
    for feed in feeds:
        if not feed.should_poll:
            logger.info("Skipping feed %s (should_poll=false)", feed.id)
            continue
        logger.info("Parsing feed %s: %s", feed.id, feed.url)
        parsed = feedparser.parse(feed.url)
        for entry in parsed.entries:
            link = str(getattr(entry, "link", "") or "")
            items.append(
                FeedItem(
                    feed_id=feed.id,
                    id=str(getattr(entry, "id", None) or link),
                    link=link,
                    thumbnail=_entry_thumbnail(entry),
                    published_at=_entry_published_at(entry).isoformat(),
                    title=str(getattr(entry, "title", "") or ""),
                    description=_entry_description(entry),
                    feed_language=feed.language or "",
                )
            )
    return items


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint (CMD main.handler)."""
    items = collect_feed_items()
    result = ingest_feed_items(items)
    logger.info(
        "Collected %s items; accepted=%s skipped=%s enqueued=%s",
        len(items),
        result.accepted,
        result.skipped_existing,
        result.enqueued,
    )
    return {
        "ok": True,
        "item_count": len(items),
        "accepted": result.accepted,
        "skipped_existing": result.skipped_existing,
        "enqueued": result.enqueued,
        "sample_titles": [item.title for item in items[:5]],
    }


def main() -> None:
    load_dotenv()
    items = collect_feed_items()
    result = ingest_feed_items(items)
    for item in items:
        print(f"{item.published_at} | {item.title} | {item.link}")
    print(
        f"total={len(items)} accepted={result.accepted} "
        f"skipped={result.skipped_existing} enqueued={result.enqueued}"
    )


if __name__ == "__main__":
    main()
