"""Structured geo/theme extraction via LangChain + Bedrock Converse."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from llm_model import get_extract_model

logger = logging.getLogger(__name__)

_PLACE_CONFIDENCE_MIN = 0.55

GeoScope = Literal["local", "regional", "national", "global"]

_structured_cache: dict[tuple[str, ...], Any] = {}


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


def _normalize_suggestion(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:64]


def _build_extract_model(allowed_slugs: list[str]):
    """Build a structured-output schema with theme_slugs constrained to allowlist."""
    key = tuple(allowed_slugs)
    cached = _structured_cache.get(key)
    if cached is not None:
        return cached

    if allowed_slugs:
        # Dynamic enum for Bedrock structured output; not a static Literal form.
        theme_slug_type = Literal[*allowed_slugs]  # ty: ignore[invalid-type-form]
        theme_field = (
            list[theme_slug_type],
            Field(
                default_factory=list,
                description=(
                    "1–3 theme slugs from the allowed enum when the story clearly "
                    "fits. Empty only when nothing applies."
                ),
            ),
        )
    else:
        theme_field = (
            list[str],
            Field(
                default_factory=list,
                description="Theme slugs (allowlist empty — leave empty).",
            ),
        )

    model = create_model(
        "PlaceThemeExtract",
        geo_scope=(
            GeoScope,
            Field(
                description=(
                    "Geographic scale of the primary event location: local (city), "
                    "regional (state/province), national (country), or global when "
                    "there is no real place focus."
                )
            ),
        ),
        places=(
            list[PlaceMention],
            Field(
                default_factory=list,
                description=(
                    "Primary event location(s). Prefer one best place. Empty when "
                    "geo_scope is global and no place applies."
                ),
            ),
        ),
        theme_slugs=theme_field,
        suggested_themes=(
            list[str],
            Field(
                default_factory=list,
                description=(
                    "Short free-form theme ideas ONLY when no allowlisted theme fits. "
                    "Never duplicate allowlisted slugs. Not attached to the article."
                ),
            ),
        ),
        story_label=(
            str,
            Field(
                default="",
                description=(
                    "Short generic ongoing-event name (3–6 words), e.g. "
                    "'Pete Hegseth Impeachment' or 'Spanish Rail Crash'. "
                    "Empty string when the article is not a clear developing story."
                ),
            ),
        ),
        __base__=BaseModel,
    )
    _structured_cache[key] = model
    return model


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

Rules for themes:
- Pick 1–3 theme_slugs from the allowed enum when the story clearly fits a ressort.
- Use suggested_themes only for gaps (ideas not in the allowlist); do not invent \
duplicates of allowlisted slugs there.
- Prefer precise beats (e.g. sports + conflict, not only geopolitics).

Rules for story_label:
- A short generic event name (about 3–6 words), not the full headline.
- Empty string when there is no clear ongoing story to cluster on.

Examples:
- Title: "Spain's king and queen attend memorial service for rail crash victims" \
→ geo_scope=national, places=[{"query":"Spain","confidence":0.9}], \
theme_slugs=["disaster"], story_label="Spanish Rail Crash"
- Title: "UK social media ban expansion for under-16s could cover YouTube Kids" \
→ geo_scope=national, places=[{"query":"United Kingdom","confidence":0.9}], \
theme_slugs=["media","politics"], story_label="UK Under-16 Social Media Ban"
- Title: "House votes to effectively end the impeachment effort against Pete Hegseth" \
→ theme_slugs=["politics"], story_label="Pete Hegseth Impeachment"
- Title: "Real Madrid's Vinícius Jr sends surprise message to boy who lost his legs \
in Sudan's war" → theme_slugs=["sports","conflict"], suggested_themes=[]
- Title: "Global stock markets mixed as investors await central bank signals" \
→ geo_scope=global, places=[], theme_slugs=["markets"], story_label=""
"""


def extract_place_and_themes(
    *,
    title: str,
    summary: str,
    themes: list[dict[str, str]] | list[str],
) -> dict[str, Any]:
    """Return geo_scope, place, allowlisted themes, suggestions, story_label.

    ``themes`` may be ``[{"slug","label"}, ...]`` or bare slug strings.
    Failures raise; callers may catch and fall back to global / no themes.
    """
    pairs: list[tuple[str, str]] = []
    for item in themes:
        if isinstance(item, dict):
            slug = str(item.get("slug") or "").strip()
            label = str(item.get("label") or slug).strip()
        else:
            slug = str(item).strip()
            label = slug
        if slug:
            pairs.append((slug, label or slug))
    # Stable unique order by slug
    seen: set[str] = set()
    unique_pairs: list[tuple[str, str]] = []
    for slug, label in sorted(pairs, key=lambda p: p[0]):
        if slug not in seen:
            seen.add(slug)
            unique_pairs.append((slug, label))
    allowed = [slug for slug, _ in unique_pairs]
    allowed_set = set(allowed)

    catalog = [{"slug": s, "label": lab} for s, lab in unique_pairs]
    user = (
        f"Allowed themes (slug — label): {json.dumps(catalog)}\n\n"
        f"Title: {title}\n\nSummary: {summary[:1500]}"
    )
    schema = _build_extract_model(allowed)
    structured = get_extract_model().with_structured_output(schema)
    result = structured.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user),
        ]
    )
    if not isinstance(result, BaseModel):
        result = schema.model_validate(result)

    data = result.model_dump()
    scope = str(data.get("geo_scope") or "global").strip().lower()
    if scope not in {"local", "regional", "national", "global"}:
        scope = "global"

    place_query = ""
    confidence = 0.0
    places = data.get("places") or []
    if isinstance(places, list) and places:
        first = places[0] if isinstance(places[0], dict) else {}
        place_query = str(first.get("query") or "").strip()
        try:
            confidence = float(first.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

    if not place_query or confidence < _PLACE_CONFIDENCE_MIN:
        place_query = ""
        confidence = 0.0

    themes_out: list[str] = []
    for slug in data.get("theme_slugs") or []:
        # Enum values may come back as enum members or strings
        s = str(getattr(slug, "value", slug)).strip()
        if s in allowed_set and s not in themes_out:
            themes_out.append(s)

    suggestions: list[str] = []
    for raw in data.get("suggested_themes") or []:
        norm = _normalize_suggestion(str(raw))
        if not norm or norm in allowed_set or norm in suggestions:
            continue
        suggestions.append(norm)

    story_label = str(data.get("story_label") or "").strip()[:120]

    return {
        "geo_scope": scope,
        "place_query": place_query,
        "geo_confidence": confidence if place_query else None,
        "theme_slugs": themes_out,
        "suggested_themes": suggestions,
        "story_label": story_label,
    }
