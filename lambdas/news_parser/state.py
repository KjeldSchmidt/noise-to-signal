"""LangGraph state for news_parser enrichment."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class EnrichState(TypedDict):
    # From FeedItem (always present at invoke)
    feed_id: int
    url: str
    raw_title: str
    raw_description: str
    published_at: str
    image_url: str
    feed_language: NotRequired[str]

    # normalize
    title: NotRequired[str]
    summary: NotRequired[str]

    # embed (parallel branch)
    embedding: NotRequired[list[float]]
    embedding_model: NotRequired[str]

    # extract_place (parallel branch)
    geo_level: NotRequired[str]
    place_label: NotRequired[str]
    country_code: NotRequired[str]
    admin1: NotRequired[str]
    locality: NotRequired[str]
    latitude: NotRequired[float | None]
    longitude: NotRequired[float | None]
    geo_confidence: NotRequired[float | None]
    theme_slugs: NotRequired[list[str]]
    suggested_themes: NotRequired[list[str]]
    story_label: NotRequired[str]
    impact_tier: NotRequired[str]
    impact_rationale: NotRequired[str]
    extract_model: NotRequired[str]
    enrichment_status: NotRequired[str]

    # upsert result
    created: NotRequired[bool]
    article_id: NotRequired[int]
    story_thread_id: NotRequired[int | None]
