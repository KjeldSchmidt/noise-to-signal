"""Structured output for brief evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

BriefPickKind = Literal["article", "thread"]


class BriefPick(BaseModel):
    candidate_id: str = Field(
        description="Stable id from the candidate list, e.g. article:12 or thread:5."
    )
    rank: int
    score: float = Field(ge=0.0, le=1.0, default=0.7)
    reason: str = Field(min_length=1, max_length=400)

    @field_validator("rank")
    @classmethod
    def _rank_ok(cls, value: int) -> int:
        if value < 1:
            raise ValueError("rank must be >= 1")
        return value

    @field_validator("candidate_id")
    @classmethod
    def _candidate_id_ok(cls, value: str) -> str:
        text = (value or "").strip()
        if not text.startswith("article:") and not text.startswith("thread:"):
            raise ValueError("candidate_id must be article:<id> or thread:<id>")
        suffix = text.split(":", 1)[1]
        if not suffix.isdigit() or int(suffix) < 1:
            raise ValueError("candidate_id must include a positive integer id")
        return text

    def parsed_kind(self) -> BriefPickKind:
        return "thread" if self.candidate_id.startswith("thread:") else "article"

    def parsed_id(self) -> int:
        return int(self.candidate_id.split(":", 1)[1])


class BriefSelection(BaseModel):
    items: list[BriefPick] = Field(default_factory=list, max_length=10)
