"""Contracts for /api/internal/feeds/."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Feed:
    id: int
    title: str
    url: str
    site_url: str
    description: str
    category: str
    kind: str
    owner_id: int | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class FeedListResponse:
    feeds: list[Feed]
