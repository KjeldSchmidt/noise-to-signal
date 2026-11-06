"""Contracts for feed item ingest and article upsert."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeedItem(BaseModel):
    """One RSS entry discovered by feed_consumer."""

    model_config = ConfigDict(frozen=True)

    feed_id: int
    id: str
    link: str
    title: str
    description: str
    published_at: str  # ISO-8601
    thumbnail: str = ""


class FeedItemIngestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[FeedItem] = Field(default_factory=list)


class FeedItemIngestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: int
    skipped_existing: int
    enqueued: int


class ArticleUpsert(BaseModel):
    """Enriched article written by news_parser."""

    model_config = ConfigDict(frozen=True)

    feed_id: int
    url: str
    title: str
    summary: str
    published_at: str  # ISO-8601
    image_url: str = ""


class ArticleUpsertResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    created: bool
    article_id: int
