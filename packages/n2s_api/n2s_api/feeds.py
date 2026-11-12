"""Contracts for /api/internal/feeds/."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Feed(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    url: str
    site_url: str
    description: str
    category: str
    kind: str
    owner_id: int | None
    is_active: bool
    language: str = "en"
    should_poll: bool = True


class FeedListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    feeds: list[Feed]
