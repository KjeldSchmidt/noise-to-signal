"""RSS feed consumer — Lambda handler + local runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import feedparser
from dotenv import load_dotenv

from web_api import list_feeds

logger = logging.getLogger(__name__)


@dataclass
class FeedItem:
    id: str
    link: str
    thumbnail: str
    date: datetime
    title: str
    description: str


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
    """Fetch active feed list from the web API and parse each RSS URL."""
    items: list[FeedItem] = []
    feeds = list_feeds()
    for feed in feeds:
        logger.info("Parsing feed %s: %s", feed.id, feed.url)
        parsed = feedparser.parse(feed.url)
        for entry in parsed.entries:
            published = getattr(entry, "published_parsed", None)
            if published:
                date = datetime(*published[:6])
            else:
                date = datetime.now(timezone.utc)
            items.append(
                FeedItem(
                    id=str(getattr(entry, "id", None) or getattr(entry, "link", "")),
                    link=str(getattr(entry, "link", "") or ""),
                    thumbnail=_entry_thumbnail(entry),
                    date=date,
                    title=str(getattr(entry, "title", "") or ""),
                    description=_entry_description(entry),
                )
            )
    return items


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint (CMD main.handler)."""
    items = collect_feed_items()
    logger.info("Collected %s feed items from %s event", len(items), type(event).__name__)
    return {
        "ok": True,
        "item_count": len(items),
        # Keep payload small — full bodies belong in a later persistence step.
        "sample_titles": [item.title for item in items[:5]],
    }


def main() -> None:
    load_dotenv()
    items = collect_feed_items()
    for item in items:
        print(f"{item.date.isoformat()} | {item.title} | {item.link}")
    print(f"total={len(items)}")


if __name__ == "__main__":
    main()
