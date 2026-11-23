"""Structured output for brief evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class BriefPick(BaseModel):
    article_id: int
    rank: int
    score: float = Field(ge=0.0, le=1.0, default=0.7)
    reason: str = Field(min_length=1, max_length=400)

    @field_validator("rank")
    @classmethod
    def _rank_ok(cls, value: int) -> int:
        if value < 1:
            raise ValueError("rank must be >= 1")
        return value


class BriefSelection(BaseModel):
    items: list[BriefPick] = Field(default_factory=list, max_length=10)
