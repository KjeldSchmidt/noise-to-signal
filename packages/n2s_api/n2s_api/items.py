"""Contracts for feed item ingest and article upsert."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    embedding: list[float] | None = None
    embedding_model: str = ""
    enrichment_status: str = ""
    extract_model: str = ""
    geo_level: str = "global"
    place_label: str = ""
    country_code: str = ""
    admin1: str = ""
    locality: str = ""
    latitude: float | None = None
    longitude: float | None = None
    geo_confidence: float | None = None
    story_label: str = ""
    impact_tier: str = ""
    impact_rationale: str = ""
    theme_slugs: list[str] = Field(default_factory=list)
    suggested_themes: list[str] = Field(default_factory=list)

    @field_validator("embedding")
    @classmethod
    def _embedding_dims(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 1024:
            raise ValueError("embedding must have exactly 1024 dimensions")
        return value

    @field_validator("country_code")
    @classmethod
    def _country_code(cls, value: str) -> str:
        return (value or "").strip().lower()[:2]

    @field_validator("geo_level")
    @classmethod
    def _geo_level(cls, value: str) -> str:
        allowed = {"global", "country", "admin1", "locality"}
        v = (value or "global").strip().lower()
        return v if v in allowed else "global"

    @field_validator("enrichment_status")
    @classmethod
    def _enrichment_status(cls, value: str) -> str:
        allowed = {"", "ok", "degraded"}
        v = (value or "").strip().lower()
        return v if v in allowed else ""

    @field_validator("impact_tier")
    @classmethod
    def _impact_tier(cls, value: str) -> str:
        allowed = {"", "commercial", "ephemeral", "notable", "major"}
        v = (value or "").strip().lower()
        return v if v in allowed else ""

    @field_validator("impact_rationale")
    @classmethod
    def _impact_rationale(cls, value: str) -> str:
        return (value or "").strip()[:160]


class ArticleUpsertResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    created: bool
    article_id: int
    story_thread_id: int | None = None


class ThemeDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    label: str


class ThemeListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    themes: list[ThemeDTO] = Field(default_factory=list)


class GeocodeSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    q: str
    limit: int = 5
    lang: str = "en"
    scope_hint: str = ""


class GeocodePlace(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    latitude: float
    longitude: float
    country_code: str = ""
    admin1: str = ""
    locality: str = ""
    geo_level: str = "locality"
    osm_class: str = ""
    osm_type: str = ""
    importance: float | None = None


class GeocodeSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[GeocodePlace] = Field(default_factory=list)
