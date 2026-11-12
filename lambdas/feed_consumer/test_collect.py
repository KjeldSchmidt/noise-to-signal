"""Tests for conditional RSS fetch / poll-state collection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from n2s_api import Feed, FeedPollStateUpdate

from main import (
    _entries_from_parsed,
    _poll_state_update_if_changed,
    collect_feed_items,
)


def _feed(**overrides: Any) -> Feed:
    base: dict[str, Any] = {
        "id": 1,
        "title": "BBC",
        "url": "https://example.com/rss.xml",
        "site_url": "https://example.com",
        "description": "",
        "category": "World",
        "kind": "curated",
        "owner_id": None,
        "is_active": True,
        "language": "en",
        "should_poll": True,
        "http_etag": "",
        "http_last_modified": "",
    }
    base.update(overrides)
    return Feed(**base)


def test_entries_from_parsed_skips_304() -> None:
    parsed = SimpleNamespace(status=304, entries=[{"title": "should not appear"}])
    assert _entries_from_parsed(_feed(), parsed) == []


def test_entries_from_parsed_maps_200() -> None:
    entry = SimpleNamespace(
        id="guid-1",
        link="https://example.com/a",
        title="Hello",
        summary="World",
        published_parsed=(2026, 11, 12, 10, 0, 0, 0, 0, -1),
        media_thumbnail=None,
        media_content=None,
        enclosures=None,
        summary_detail=None,
    )
    parsed = SimpleNamespace(status=200, entries=[entry])
    items = _entries_from_parsed(_feed(), parsed)
    assert len(items) == 1
    assert items[0].link == "https://example.com/a"
    assert items[0].title == "Hello"
    assert items[0].feed_id == 1


def test_poll_state_update_skips_empty_validators() -> None:
    feed = _feed(http_etag='"old"', http_last_modified="Wed, 12 Nov 2025 10:00:00 GMT")
    parsed = SimpleNamespace(status=304, etag=None, modified=None, headers={})
    assert _poll_state_update_if_changed(feed, parsed) is None


def test_poll_state_update_when_etag_changes() -> None:
    feed = _feed(http_etag='"old"')
    parsed = SimpleNamespace(
        status=200,
        etag='"new"',
        modified=None,
        headers={"last-modified": "Thu, 13 Nov 2025 11:00:00 GMT"},
    )
    update = _poll_state_update_if_changed(feed, parsed)
    assert update == FeedPollStateUpdate(
        feed_id=1,
        http_etag='"new"',
        http_last_modified="Thu, 13 Nov 2025 11:00:00 GMT",
    )


def test_collect_feed_items_304_and_200() -> None:
    feeds = [
        _feed(id=1, url="https://example.com/a.xml", http_etag='"a1"'),
        _feed(id=2, url="https://example.com/b.xml"),
    ]
    entry = SimpleNamespace(
        id="g2",
        link="https://example.com/b",
        title="New",
        summary="",
        published_parsed=(2026, 11, 12, 12, 0, 0, 0, 0, -1),
        media_thumbnail=None,
        media_content=None,
        enclosures=None,
        summary_detail=None,
    )
    parsed_304 = SimpleNamespace(status=304, entries=[], etag=None, modified=None, headers={})
    parsed_200 = SimpleNamespace(
        status=200,
        entries=[entry],
        etag='"b1"',
        modified=None,
        headers={"Last-Modified": "Thu, 13 Nov 2025 12:00:00 GMT"},
    )

    with (
        patch("main.list_feeds", return_value=feeds),
        patch("main._parse_feed", side_effect=[parsed_304, parsed_200]) as parse_mock,
    ):
        items, poll_updates = collect_feed_items()

    assert parse_mock.call_count == 2
    assert [i.link for i in items] == ["https://example.com/b"]
    assert poll_updates == [
        FeedPollStateUpdate(
            feed_id=2,
            http_etag='"b1"',
            http_last_modified="Thu, 13 Nov 2025 12:00:00 GMT",
        )
    ]


def test_collect_skips_should_not_poll() -> None:
    feeds = [_feed(should_poll=False)]
    with (
        patch("main.list_feeds", return_value=feeds),
        patch("main._parse_feed") as parse_mock,
    ):
        items, poll_updates = collect_feed_items()
    parse_mock.assert_not_called()
    assert items == []
    assert poll_updates == []
