"""Unit tests for LangGraph enrich nodes (mocked I/O)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from graph import embed, extract_place, normalize, upsert


def test_normalize_cleans_and_truncates_title() -> None:
    out = normalize(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "  Hello <b>World</b>  ",
            "raw_description": "<p>Summary here</p>",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
        }
    )
    assert out["title"] == "Hello World"
    assert out["summary"] == "Summary here"


@patch("graph.embed_text", return_value=[0.1] * 1024)
def test_embed_writes_vector_and_model(mock_embed: MagicMock) -> None:
    out = embed(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "Title",
            "summary": "Summary",
        }
    )
    mock_embed.assert_called_once()
    assert len(out["embedding"]) == 1024
    assert out["embedding_model"] == "cohere.embed-multilingual-v3"


@patch("graph._active_themes", return_value=[{"slug": "tech", "label": "Technology"}])
@patch("graph.extract_place_and_themes", side_effect=RuntimeError("bedrock down"))
def test_extract_place_soft_fails_to_global(
    _mock_extract: MagicMock, _mock_themes: MagicMock
) -> None:
    out = extract_place(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "Title",
            "summary": "Summary",
        }
    )
    assert out["geo_level"] == "global"
    assert out["theme_slugs"] == []
    assert out["latitude"] is None


@patch("graph._active_themes", return_value=[{"slug": "tech", "label": "Technology"}])
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "local",
        "place_query": "Cologne, Germany",
        "geo_confidence": 0.9,
        "theme_slugs": ["tech"],
        "suggested_themes": [],
        "story_label": "",
    },
)
@patch("graph.geocode_search")
def test_extract_place_geocodes_when_confident(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    hit = MagicMock()
    hit.geo_level = "locality"
    hit.label = "Cologne, NRW, Germany"
    hit.country_code = "de"
    hit.admin1 = "North Rhine-Westphalia"
    hit.locality = "Cologne"
    hit.latitude = 50.94
    hit.longitude = 6.96
    mock_geocode.return_value = [hit]

    out = extract_place(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "News from Cologne",
            "summary": "Something local",
        }
    )
    assert out["geo_level"] == "locality"
    assert out["place_label"] == "Cologne, NRW, Germany"
    assert out["theme_slugs"] == ["tech"]
    assert out["latitude"] == 50.94


@patch(
    "graph._active_themes",
    return_value=[{"slug": "politics", "label": "Politics"}],
)
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "global",
        "place_query": "Spain",
        "geo_confidence": 0.9,
        "theme_slugs": ["politics"],
        "suggested_themes": ["royal-news"],
        "story_label": "Spanish Rail Crash",
    },
)
@patch("graph.geocode_search")
def test_extract_place_geocodes_despite_global_scope(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    hit = MagicMock()
    hit.geo_level = "country"
    hit.label = "Spain"
    hit.country_code = "es"
    hit.admin1 = ""
    hit.locality = ""
    hit.latitude = 40.0
    hit.longitude = -3.0
    mock_geocode.return_value = [hit]

    out = extract_place(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "Spain memorial",
            "summary": "Leaders gathered after the crash.",
        }
    )
    mock_geocode.assert_called_once_with("Spain", limit=1, scope_hint="")
    assert out["geo_level"] == "country"
    assert out["place_label"] == "Spain"
    assert out["country_code"] == "es"
    assert out["latitude"] == 40.0
    assert out["suggested_themes"] == ["royal-news"]
    assert out["story_label"] == "Spanish Rail Crash"


@patch("graph.upsert_article")
def test_upsert_builds_article_and_returns_ids(mock_upsert: MagicMock) -> None:
    mock_upsert.return_value = MagicMock(created=True, article_id=42, story_thread_id=7)
    state: dict[str, Any] = {
        "feed_id": 1,
        "url": "https://example.com/a",
        "raw_title": "t",
        "raw_description": "d",
        "published_at": "2026-01-01T00:00:00Z",
        "image_url": "",
        "title": "Title",
        "summary": "Summary",
        "embedding": [0.0] * 1024,
        "embedding_model": "cohere.embed-multilingual-v3",
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
    out = upsert(state)  # ty: ignore[invalid-argument-type]
    mock_upsert.assert_called_once()
    assert out == {
        "created": True,
        "article_id": 42,
        "story_thread_id": 7,
    }
