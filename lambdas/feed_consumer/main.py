"""RSS feed consumer — Lambda handler + local runner."""

from __future__ import annotations

import calendar
import http.client
import logging
import urllib.request
from datetime import UTC, datetime
from email.utils import formatdate
from typing import Any

import feedparser
from dotenv import load_dotenv
from n2s_api import Feed, FeedItem, FeedPollStateUpdate
from n2s_web_client import ingest_feed_items, list_feeds, update_feed_poll_state

logger = logging.getLogger(__name__)

RSS_FETCH_TIMEOUT_S = 15.0


class _TimeoutHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:  # type: ignore[override]
        return self.do_open(http.client.HTTPConnection, req, timeout=self._timeout)


class _TimeoutHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:  # type: ignore[override]
        return self.do_open(http.client.HTTPSConnection, req, timeout=self._timeout)


def _rss_handlers(*, timeout: float = RSS_FETCH_TIMEOUT_S) -> list[urllib.request.BaseHandler]:
    return [_TimeoutHTTPHandler(timeout), _TimeoutHTTPSHandler(timeout)]


def _header_str(value: Any) -> str:
    """Normalize feedparser etag/modified values to short header strings."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    # feedparser may return Last-Modified as struct_time / 9-tuple.
    try:
        parts = tuple(value)[:9]
        if len(parts) >= 6:
            ts = calendar.timegm(parts)  # type: ignore[arg-type]
            return formatdate(timeval=ts, usegmt=True)
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return str(value).strip()


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


def _poll_validators_from_parsed(parsed: Any) -> tuple[str, str]:
    etag = _header_str(getattr(parsed, "etag", None))
    # Prefer raw HTTP header when present; fall back to feedparser's modified value.
    headers = getattr(parsed, "headers", None) or {}
    modified = ""
    if isinstance(headers, dict):
        modified = _header_str(headers.get("last-modified") or headers.get("Last-Modified"))
    if not modified:
        modified = _header_str(getattr(parsed, "modified", None))
    return etag, modified


def _poll_state_update_if_changed(feed: Feed, parsed: Any) -> FeedPollStateUpdate | None:
    """Build a poll-state update when the origin returned new validators.

    Never clear stored validators on 304 responses that omit etag/modified.
    """
    etag, modified = _poll_validators_from_parsed(parsed)
    if not etag and not modified:
        return None
    new_etag = etag or (feed.http_etag or "")
    new_modified = modified or (feed.http_last_modified or "")
    if new_etag == (feed.http_etag or "") and new_modified == (feed.http_last_modified or ""):
        return None
    return FeedPollStateUpdate(
        feed_id=feed.id,
        http_etag=new_etag,
        http_last_modified=new_modified,
    )


def _parse_feed(feed: Feed) -> Any:
    kwargs: dict[str, Any] = {
        "handlers": _rss_handlers(),
    }
    if feed.http_etag:
        kwargs["etag"] = feed.http_etag
    if feed.http_last_modified:
        kwargs["modified"] = feed.http_last_modified
    return feedparser.parse(feed.url, **kwargs)


def _entries_from_parsed(feed: Feed, parsed: Any) -> list[FeedItem]:
    status = int(getattr(parsed, "status", 0) or 0)
    if status == 304:
        logger.info("Feed %s unchanged (304)", feed.id)
        return []

    items: list[FeedItem] = []
    for entry in getattr(parsed, "entries", None) or []:
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


def collect_feed_items() -> tuple[list[FeedItem], list[FeedPollStateUpdate]]:
    """Fetch feed list from the web API and parse each RSS URL (conditional GET)."""
    items: list[FeedItem] = []
    poll_updates: list[FeedPollStateUpdate] = []
    feeds = list_feeds()
    for feed in feeds:
        if not feed.should_poll:
            logger.info("Skipping feed %s (should_poll=false)", feed.id)
            continue
        logger.info("Parsing feed %s: %s", feed.id, feed.url)
        try:
            parsed = _parse_feed(feed)
        except Exception:
            logger.exception("Failed to parse feed %s (%s)", feed.id, feed.url)
            continue

        update = _poll_state_update_if_changed(feed, parsed)
        if update is not None:
            poll_updates.append(update)

        items.extend(_entries_from_parsed(feed, parsed))
    return items, poll_updates


def _run_once() -> dict[str, Any]:
    items, poll_updates = collect_feed_items()
    result = ingest_feed_items(items)
    poll_updated = 0
    if poll_updates:
        poll_updated = update_feed_poll_state(poll_updates).updated
    logger.info(
        "Collected %s items; accepted=%s skipped=%s enqueued=%s poll_state_updated=%s",
        len(items),
        result.accepted,
        result.skipped_existing,
        result.enqueued,
        poll_updated,
    )
    return {
        "ok": True,
        "item_count": len(items),
        "accepted": result.accepted,
        "skipped_existing": result.skipped_existing,
        "enqueued": result.enqueued,
        "poll_state_updated": poll_updated,
        "sample_titles": [item.title for item in items[:5]],
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint (CMD main.handler)."""
    return _run_once()


def main() -> None:
    load_dotenv()
    items, poll_updates = collect_feed_items()
    result = ingest_feed_items(items)
    if poll_updates:
        update_feed_poll_state(poll_updates)
    for item in items:
        print(f"{item.published_at} | {item.title} | {item.link}")
    print(
        f"accepted={result.accepted} skipped={result.skipped_existing} "
        f"enqueued={result.enqueued} poll_updates={len(poll_updates)}"
    )


if __name__ == "__main__":
    main()
