"""DTOs for personalized brief builder worker ↔ web internal API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

BriefStatus = Literal["pending", "ready", "failed"]
BriefWorkerAction = Literal[
    "build",
    "record_preference",
    "erase_preferences",
    "list_preferences",
    "delete_preference",
]


class BriefBuilderRequest(BaseModel):
    """Lambda payload from Django (Event or RequestResponse)."""

    action: BriefWorkerAction = "build"
    user_id: int
    brief_id: int | None = None
    """Required when action=build."""
    preference_text: str = ""
    """Required when action=record_preference — free-text signal for AgentCore."""
    memory_record_id: str = ""
    """Required when action=delete_preference."""

    @field_validator("user_id")
    @classmethod
    def _positive_user(cls, value: int) -> int:
        if value < 1:
            raise ValueError("user_id must be positive")
        return value


class BriefCandidateDTO(BaseModel):
    article_id: int
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published_at: str = ""
    impact_tier: str = ""
    story_label: str = ""
    place_label: str = ""
    country_code: str = ""
    themes: list[str] = Field(default_factory=list)
    score: float = 0.0


class BriefLocationDTO(BaseModel):
    label: str
    country_code: str = ""
    admin1: str = ""
    locality: str = ""
    geo_level: str = ""


class BriefFeedbackDTO(BaseModel):
    article_id: int
    title: str
    verdict: str


class BriefTasteDTO(BaseModel):
    question: str
    answer: str


class BriefThemeAffinityDTO(BaseModel):
    slug: str
    label: str
    more_count: int = 0
    less_count: int = 0
    weight: float = 0.0


class BriefUserContextResponse(BaseModel):
    user_id: int
    languages: list[str] = Field(default_factory=list)
    locations: list[BriefLocationDTO] = Field(default_factory=list)
    taste_answers: list[BriefTasteDTO] = Field(default_factory=list)
    recent_feedback: list[BriefFeedbackDTO] = Field(default_factory=list)
    theme_affinities: list[BriefThemeAffinityDTO] = Field(default_factory=list)
    candidates: list[BriefCandidateDTO] = Field(default_factory=list)


class PreferenceMemoryDTO(BaseModel):
    id: str
    text: str


class BriefItemUpsert(BaseModel):
    article_id: int
    rank: int
    score: float = 0.0
    reason: str = ""

    @field_validator("rank")
    @classmethod
    def _rank_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("rank must be >= 1")
        return value


class BriefCompleteRequest(BaseModel):
    brief_id: int
    user_id: int
    status: Literal["ready", "failed"]
    error: str = ""
    items: list[BriefItemUpsert] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def _ready_needs_items(
        cls, value: list[BriefItemUpsert], info: object
    ) -> list[BriefItemUpsert]:
        return value


class BriefCompleteResponse(BaseModel):
    brief_id: int
    status: BriefStatus
    item_count: int = 0
