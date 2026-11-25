"""DTOs for personalized brief builder worker ↔ web internal API."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

BriefStatus = Literal["pending", "ready", "failed"]
BriefCandidateKind = Literal["article", "thread"]
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
    kind: BriefCandidateKind = "article"
    article_id: int
    """Article id, or lead article id when kind=thread."""
    story_thread_id: int | None = None
    title: str
    url: str = ""
    summary: str = ""
    source: str = ""
    published_at: str = ""
    impact_tier: str = ""
    story_label: str = ""
    place_label: str = ""
    country_code: str = ""
    themes: list[str] = Field(default_factory=list)
    score: float = 0.0
    article_count: int = 1

    @property
    def candidate_id(self) -> str:
        if self.kind == "thread" and self.story_thread_id is not None:
            return f"thread:{self.story_thread_id}"
        return f"article:{self.article_id}"


class BriefLocationDTO(BaseModel):
    label: str
    country_code: str = ""
    admin1: str = ""
    locality: str = ""
    geo_level: str = ""


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
    theme_affinities: list[BriefThemeAffinityDTO] = Field(default_factory=list)
    candidates: list[BriefCandidateDTO] = Field(default_factory=list)


class PreferenceMemoryDTO(BaseModel):
    id: str
    text: str


class BriefItemUpsert(BaseModel):
    kind: BriefCandidateKind = "article"
    article_id: int | None = None
    story_thread_id: int | None = None
    rank: int
    score: float = 0.0
    reason: str = ""

    @field_validator("rank")
    @classmethod
    def _rank_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("rank must be >= 1")
        return value

    @model_validator(mode="after")
    def _xor_target(self) -> Self:
        has_article = self.article_id is not None
        has_thread = self.story_thread_id is not None
        if self.kind == "article":
            if not has_article or has_thread:
                raise ValueError("kind=article requires article_id and no story_thread_id")
        elif self.kind == "thread":
            if not has_thread:
                raise ValueError("kind=thread requires story_thread_id")
        else:
            raise ValueError(f"unknown kind: {self.kind}")
        return self


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


class StorySummarizerRequest(BaseModel):
    """Lambda payload to (re)generate a non-personal story-thread summary."""

    story_thread_id: int

    @field_validator("story_thread_id")
    @classmethod
    def _positive_thread(cls, value: int) -> int:
        if value < 1:
            raise ValueError("story_thread_id must be positive")
        return value


class StoryThreadMemberDTO(BaseModel):
    title: str
    summary: str = ""
    source: str = ""
    published_at: str = ""


class StoryThreadSummaryContextResponse(BaseModel):
    story_thread_id: int
    label: str = ""
    articles: list[StoryThreadMemberDTO] = Field(default_factory=list)


class StoryThreadSummaryUpdateRequest(BaseModel):
    story_thread_id: int
    summary: str

    @field_validator("story_thread_id")
    @classmethod
    def _positive_thread(cls, value: int) -> int:
        if value < 1:
            raise ValueError("story_thread_id must be positive")
        return value


class StoryThreadSummaryUpdateResponse(BaseModel):
    story_thread_id: int
    summarized_at: str
    summary_chars: int = 0
