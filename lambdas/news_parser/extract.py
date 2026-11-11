"""Structured geo/theme extraction via LangChain + Bedrock Converse."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from llm_model import get_extract_model

logger = logging.getLogger(__name__)

_PLACE_CONFIDENCE_MIN = 0.55

GeoScope = Literal["local", "regional", "national", "global"]


class PlaceMention(BaseModel):
    query: str = Field(
        description=(
            "English place query for OpenStreetMap Nominatim, e.g. "
            "'Cologne, Germany' or 'Spain'. Empty string if none."
        )
    )
    confidence: float = Field(
        description="Confidence that this is the primary event location, 0.0–1.0."
    )


class PlaceThemeExtract(BaseModel):
    geo_scope: GeoScope = Field(
        description=(
            "Geographic scale of the primary event location: local (city), "
            "regional (state/province), national (country), or global when "
            "there is no real place focus."
        )
    )
    places: list[PlaceMention] = Field(
        default_factory=list,
        description=(
            "Primary event location(s). Prefer one best place. Empty when "
            "geo_scope is global and no place applies."
        ),
    )
    theme_slugs: list[str] = Field(
        default_factory=list,
        description="Zero or more theme slugs chosen ONLY from the allowed list.",
    )
    story_label: str = Field(
        default="",
        description=(
            "Short generic ongoing-event name (3–6 words), e.g. "
            "'Pete Hegseth Impeachment' or 'Spanish Rail Crash'. "
            "Empty string when the article is not a clear developing story."
        ),
    )


_SYSTEM_PROMPT = """\
You classify news articles for a personal news filter.

Rules for geography:
- Tag the primary EVENT location, not the outlet's home country.
- If a specific country or city is where the story takes place, set geo_scope to \
national/regional/local and include that place — even when coverage is international.
- Use geo_scope=global ONLY when there is no meaningful geographic focus \
(e.g. abstract markets, pure science with no setting).
- Place queries must be English and Nominatim-friendly \
(e.g. "Cologne, Germany", "Spain", "United Kingdom").

Rules for story_label:
- A short generic event name (about 3–6 words), not the full headline.
- Empty string when there is no clear ongoing story to cluster on.

Examples:
- Title: "Spain's king and queen attend memorial service for rail crash victims" \
→ geo_scope=national, places=[{"query":"Spain","confidence":0.9}], \
story_label="Spanish Rail Crash"
- Title: "UK social media ban expansion for under-16s could cover YouTube Kids" \
→ geo_scope=national, places=[{"query":"United Kingdom","confidence":0.9}], \
story_label="UK Under-16 Social Media Ban"
- Title: "House votes to effectively end the impeachment effort against Pete Hegseth" \
→ story_label="Pete Hegseth Impeachment"
- Title: "Global stock markets mixed as investors await central bank signals" \
→ geo_scope=global, places=[], story_label=""

theme_slugs must be chosen ONLY from the allowed list (0 or more).
"""


def extract_place_and_themes(
    *,
    title: str,
    summary: str,
    theme_slugs: list[str],
) -> dict[str, Any]:
    """Return geo_scope, optional place query, confidence, themes, story_label.

    Failures raise; callers may catch and fall back to global / no themes.
    """
    allowed = sorted({s.strip() for s in theme_slugs if s.strip()})
    user = (
        f"Allowed theme_slugs: {json.dumps(allowed)}\n\nTitle: {title}\n\nSummary: {summary[:1500]}"
    )
    structured = get_extract_model().with_structured_output(PlaceThemeExtract)
    result = structured.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user),
        ]
    )
    if not isinstance(result, PlaceThemeExtract):
        result = PlaceThemeExtract.model_validate(result)

    scope: GeoScope = result.geo_scope
    if scope not in {"local", "regional", "national", "global"}:
        scope = "global"

    place_query = ""
    confidence = 0.0
    if result.places:
        first = result.places[0]
        place_query = (first.query or "").strip()
        try:
            confidence = float(first.confidence)
        except (TypeError, ValueError):
            confidence = 0.0

    # Keep a place even when scope is global — geocode decides stored geo_level.
    if not place_query or confidence < _PLACE_CONFIDENCE_MIN:
        place_query = ""
        confidence = 0.0

    allowed_set = set(allowed)
    themes: list[str] = []
    for slug in result.theme_slugs:
        s = str(slug).strip()
        if s in allowed_set and s not in themes:
            themes.append(s)

    story_label = (result.story_label or "").strip()[:120]

    return {
        "geo_scope": scope,
        "place_query": place_query,
        "geo_confidence": confidence if place_query else None,
        "theme_slugs": themes,
        "story_label": story_label,
    }
