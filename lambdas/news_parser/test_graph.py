"""Unit tests for LangGraph enrich nodes (mocked I/O)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from n2s_api import GeocodePlace

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
def test_extract_place_llm_failure_raises(
    _mock_extract: MagicMock, _mock_themes: MagicMock
) -> None:
    import pytest

    with pytest.raises(RuntimeError, match="bedrock down"):
        extract_place(
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


@patch("graph._active_themes", return_value=[{"slug": "tech", "label": "Technology"}])
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "local",
        "place_query": "Cologne, Germany",
        "country_hint": "DE",
        "mention_basis": "explicit",
        "theme_slugs": ["tech"],
        "suggested_themes": [],
        "story_label": "",
        "impact_tier": "notable",
        "impact_rationale": "Acute local hazard.",
    },
)
@patch("graph.geocode_search")
def test_extract_place_geocodes_when_explicit(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    mock_geocode.return_value = [
        GeocodePlace(
            label="Cologne, NRW, Germany",
            latitude=50.94,
            longitude=6.96,
            country_code="de",
            admin1="North Rhine-Westphalia",
            locality="Cologne",
            geo_level="locality",
            osm_class="place",
            osm_type="city",
            importance=0.72,
        )
    ]

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
    mock_geocode.assert_called_once_with("Cologne, Germany", limit=5, scope_hint="local")
    assert out["geo_level"] == "locality"
    assert out["place_label"] == "Cologne, NRW, Germany"
    assert out["theme_slugs"] == ["tech"]
    assert out["latitude"] == 50.94
    assert out["geo_confidence"] == 1.0
    assert out["impact_tier"] == "notable"
    assert out["impact_rationale"] == "Acute local hazard."
    assert out["enrichment_status"] == "ok"
    assert out["extract_model"]


@patch(
    "graph._active_themes",
    return_value=[{"slug": "politics", "label": "Politics"}],
)
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "global",
        "place_query": "Spain",
        "country_hint": "ES",
        "mention_basis": "explicit",
        "theme_slugs": ["politics"],
        "suggested_themes": ["royal-news"],
        "story_label": "Spanish Rail Crash",
        "impact_tier": "notable",
        "impact_rationale": "National disaster aftermath.",
    },
)
@patch("graph.geocode_search")
def test_extract_place_geocodes_despite_global_scope(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    mock_geocode.return_value = [
        GeocodePlace(
            label="Spain",
            latitude=40.0,
            longitude=-3.0,
            country_code="es",
            admin1="",
            locality="",
            geo_level="country",
            osm_class="boundary",
            osm_type="administrative",
            importance=0.9,
        )
    ]

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
    mock_geocode.assert_called_once_with("Spain", limit=5, scope_hint="")
    assert out["geo_level"] == "country"
    assert out["place_label"] == "Spain"
    assert out["country_code"] == "es"
    assert out["latitude"] == 40.0
    assert out["geo_confidence"] == 1.0
    assert out["suggested_themes"] == ["royal-news"]
    assert out["story_label"] == "Spanish Rail Crash"
    assert out["enrichment_status"] == "ok"


@patch("graph._active_themes", return_value=[{"slug": "climate", "label": "Climate"}])
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "global",
        "place_query": "",
        "country_hint": "",
        "mention_basis": "none",
        "theme_slugs": ["climate"],
        "suggested_themes": [],
        "story_label": "COP31 Climate Summit",
        "impact_tier": "notable",
        "impact_rationale": "Ongoing climate diplomacy.",
    },
)
@patch("graph.geocode_search")
def test_extract_place_skips_geocode_when_not_explicit(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    out = extract_place(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "COP31 kicks off",
            "summary": "Climate target overshoot.",
        }
    )
    mock_geocode.assert_not_called()
    assert out["geo_level"] == "global"
    assert out["place_label"] == ""
    assert out["geo_confidence"] is None
    assert out["impact_tier"] == "notable"
    assert out["enrichment_status"] == "ok"
    assert out["story_label"] == "COP31 Climate Summit"


@patch("graph._active_themes", return_value=[{"slug": "tech", "label": "Technology"}])
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "local",
        "place_query": "Mars",
        "country_hint": "FR",
        "mention_basis": "explicit",
        "theme_slugs": ["tech"],
        "suggested_themes": [],
        "story_label": "",
        "impact_tier": "ephemeral",
        "impact_rationale": "Human-interest science feature.",
    },
)
@patch("graph.geocode_search")
def test_extract_place_policy_discard_stays_ok_not_degraded(
    mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
    mock_geocode.return_value = [
        GeocodePlace(
            label="Mars, France",
            latitude=50.0,
            longitude=3.0,
            country_code="fr",
            admin1="",
            locality="Mars",
            geo_level="locality",
            osm_class="place",
            osm_type="village",
            importance=0.1,
        )
    ]

    out = extract_place(
        {
            "feed_id": 1,
            "url": "https://example.com/a",
            "raw_title": "t",
            "raw_description": "d",
            "published_at": "2026-01-01T00:00:00Z",
            "image_url": "",
            "title": "Mars mock mission",
            "summary": "NASA habitat.",
        }
    )
    assert out["geo_level"] == "global"
    assert out["place_label"] == ""
    assert out["locality"] == ""
    assert out["geo_confidence"] is None
    assert out["enrichment_status"] == "ok"
    assert out["theme_slugs"] == ["tech"]


@patch("graph._active_themes", return_value=[{"slug": "tech", "label": "Technology"}])
@patch(
    "graph.extract_place_and_themes",
    return_value={
        "geo_scope": "local",
        "place_query": "Cologne, Germany",
        "country_hint": "DE",
        "mention_basis": "explicit",
        "theme_slugs": ["tech"],
        "suggested_themes": [],
        "story_label": "",
        "impact_tier": "notable",
        "impact_rationale": "Acute local hazard.",
    },
)
@patch("graph.geocode_search", side_effect=RuntimeError("nominatim down"))
def test_extract_place_geocode_failure_is_degraded(
    _mock_geocode: MagicMock,
    _mock_extract: MagicMock,
    _mock_themes: MagicMock,
) -> None:
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
    assert out["geo_level"] == "global"
    assert out["theme_slugs"] == ["tech"]
    assert out["enrichment_status"] == "degraded"
    assert out["geo_confidence"] is None


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
        "impact_tier": "major",
        "impact_rationale": "Electoral shift with lasting weight.",
    }
    out = upsert(state)  # ty: ignore[invalid-argument-type]
    mock_upsert.assert_called_once()
    article = mock_upsert.call_args.args[0]
    assert article.impact_tier == "major"
    assert article.impact_rationale == "Electoral shift with lasting weight."
    assert out == {
        "created": True,
        "article_id": 42,
        "story_thread_id": 7,
    }
