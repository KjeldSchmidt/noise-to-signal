"""RSS feed consumer — Lambda handler + local runner."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import feedparser
from dotenv import load_dotenv
from n2s_api import FeedItem

from n2s_web_client import ingest_feed_items, list_feeds

logger = logging.getLogger(__name__)


def _entry_thumbnail(entry: Any) -> str:
    thumbs = getattr(entry, "media_thumbnail", None) or []
    if thumbs and isinstance(thumbs[0], dict):
        return str(thumbs[0].get("url") or "")
    return ""


def _entry_description(entry: Any) -> str:
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", None)
    if summary:
        return f"{title} - {summary}"
    detail = getattr(entry, "summary_detail", None)
    if detail is not None and getattr(detail, "value", None):
        return f"{title} - {detail.value}"
    return title


def collect_feed_items() -> list[FeedItem]:
    """Fetch feed list from the web API and parse each RSS URL."""
    items: list[FeedItem] = []
    feeds = list_feeds()
    for feed in feeds:
        if not feed.is_active:
            continue
        logger.info("Parsing feed %s: %s", feed.id, feed.url)
        parsed = feedparser.parse(feed.url)
        for entry in parsed.entries:
            published = getattr(entry, "published_parsed", None)
            if published:
                date = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                date = datetime.now(timezone.utc)
            link = str(getattr(entry, "link", "") or "")
            items.append(
                FeedItem(
                    feed_id=feed.id,
                    id=str(getattr(entry, "id", None) or link),
                    link=link,
                    thumbnail=_entry_thumbnail(entry),
                    published_at=date.isoformat(),
                    title=str(getattr(entry, "title", "") or ""),
                    description=_entry_description(entry),
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
