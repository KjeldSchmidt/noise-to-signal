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

GeoScope = Literal["local", "regional", "national", "global"]
MentionBasis = Literal["explicit", "none"]
ImpactTier = Literal["commercial", "ephemeral", "notable", "major"]

_structured_cache: dict[tuple[str, ...], Any] = {}


class PlaceMention(BaseModel):
    query: str = Field(
        description=(
            "English place query for OpenStreetMap Nominatim, e.g. "
            "'Cologne, Germany' or 'Spain'. Empty string if none. "
            "Sub-national places must be country-qualified."
        )
    )
    mention_basis: MentionBasis = Field(
        default="none",
        description=(
            "'explicit' only when the primary event location is named in the "
            "title/summary as a real Earth place. Use 'none' when omitting."
        ),
    )
    country_hint: str = Field(
        default="",
        description=(
            "ISO 3166-1 alpha-2 country code for the place (e.g. 'DE', 'ES'). "
            "Required when mention_basis is explicit; empty otherwise."
        ),
    )


def _normalize_suggestion(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:64]


def _normalize_country_hint(raw: str) -> str:
    code = re.sub(r"[^A-Za-z]", "", (raw or "").strip())[:2]
    return code.upper() if len(code) == 2 else ""


def _normalize_impact_tier(raw: str) -> ImpactTier:
    v = (raw or "").strip().lower()
    if v == "commercial":
        return "commercial"
    if v == "notable":
        return "notable"
    if v == "major":
        return "major"
    return "ephemeral"


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
                default="global",
                description=(
                    "Geographic scale of the primary event location: local (city), "
                    "regional (state/province), national (country), or global when "
                    "there is no real place focus. Default global if unsure."
                ),
            ),
        ),
        places=(
            list[PlaceMention],
            Field(
                default_factory=list,
                description=(
                    "Primary event location(s). Prefer one best place. Empty when "
                    "geo_scope is global and no place applies, or when the locus is "
                    "not an explicit real-world place named in the text."
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
        impact_tier=(
            ImpactTier,
            Field(
                default="ephemeral",
                description=(
                    "User-agnostic lasting importance: commercial (promo/deal/gift guide), "
                    "ephemeral (short half-life), notable (domain-significant), or major "
                    "(international/lasting civic or systemic). When unsure, choose the "
                    "lower tier."
                ),
            ),
        ),
        impact_rationale=(
            str,
            Field(
                default="",
                description=("One short sentence explaining the impact_tier choice (admin debug)."),
            ),
        ),
        __base__=BaseModel,
    )
    _structured_cache[key] = model
    return model


_SYSTEM_PROMPT = """\
You classify news articles for a personal news filter.

Rules for language:
- Titles and summaries may be in any language (English, French, German, etc.).
- Always understand the article in its original language, then emit structured \
fields in English.
- Place queries MUST be English and Nominatim-friendly \
(e.g. "Cologne, Germany", "Spain", "United Kingdom") even when the source text \
uses another language (e.g. "Köln" → "Cologne, Germany").
- story_label MUST be English (3–6 words), never leave it in the source language.

Rules for geography:
- Tag the primary EVENT location only when it is an explicit real-world Earth place \
named in the title or summary.
- Prefer omit (geo_scope=global, places=[]) over a guessed or invented place. \
Wrong place is worse than no place.
- Do NOT invent host cities for conferences, summits, or acronyms (e.g. COP31).
- Do NOT treat celestial bodies, mission names, metaphors, brands, or fictional \
places as geography (e.g. a "Mars" mock mission is not a place on Earth).
- If a specific country or city is where the story takes place, set geo_scope to \
national/regional/local and include that place — even when coverage is international.
- Use geo_scope=global when there is no meaningful geographic focus \
(e.g. abstract markets, pure science with no Earth setting, global climate talks).
- Sub-national queries MUST be country-qualified ("Cologne, Germany", not "Cologne").
- When emitting a place, set mention_basis=explicit and country_hint to the ISO-2 \
code (e.g. ES, GB, DE). National places use that country's own code.

Rules for themes:
- Pick 1–3 theme_slugs from the allowed enum when the story clearly fits a ressort.
- Use suggested_themes only for gaps (ideas not in the allowlist); do not invent \
duplicates of allowlisted slugs there.
- Prefer precise beats (e.g. sports + conflict, not only geopolitics).

Rules for story_label:
- A short generic English event name (about 3–6 words), not the full headline.
- Empty string when there is no clear ongoing story to cluster on.

Rules for impact (user-agnostic lasting importance — not personal taste):
- commercial: promo, deal, gift guide, affiliate-shaped selling.
- ephemeral: real-ish content with short half-life and little structural weight \
(routine updates, soft lifestyle without lasting stakes).
- notable: acute or domain-significant; worth knowing if you follow the topic \
(including culturally huge niche subjects).
- major: international / lasting civic or systemic importance (elections, wars, \
major policy or market structure shifts, large disasters).
- Judge event substance, not outlet prestige, urgency language, or virality.
- Prefer commercial when the piece is primarily selling.
- When unsure between two tiers, choose the lower one (precision for major).

Examples:
- Title: "Spain's king and queen attend memorial service for rail crash victims" \
→ geo_scope=national, \
places=[{"query":"Spain","mention_basis":"explicit","country_hint":"ES"}], \
theme_slugs=["disaster"], story_label="Spanish Rail Crash", \
impact_tier=notable, impact_rationale="National disaster aftermath with civic weight."
- Title: "Flood warnings issued as Rhine rises in Cologne" \
→ geo_scope=local, \
places=[{"query":"Cologne, Germany","mention_basis":"explicit","country_hint":"DE"}], \
theme_slugs=["climate"], story_label="", \
impact_tier=notable, impact_rationale="Acute local hazard with real consequences."
- Title: "The 37 best Christmas gifts in the UK for tweens – chosen by 10- to 12-year-olds" \
→ geo_scope=global, places=[], theme_slugs=[], story_label="", \
impact_tier=commercial, impact_rationale="Seasonal gift guide primarily selling products."
- Title: "Sharge's eye-catching MacBook charger is over 25 percent off" \
→ geo_scope=global, places=[], theme_slugs=[], story_label="", \
impact_tier=commercial, impact_rationale="Product discount promo."
- Title: "How years of research built Grand Theft Auto VI's obsessively detailed world" \
→ geo_scope=global, places=[], theme_slugs=[], story_label="", \
impact_tier=notable, \
impact_rationale="Domain feature on a culturally massive game release."
- Title: "Midterms: Blue Tsunami turns Texas Democrat" \
→ geo_scope=national, \
places=[{"query":"United States","mention_basis":"explicit","country_hint":"US"}], \
theme_slugs=["politics"], story_label="US Midterm Elections", \
impact_tier=major, \
impact_rationale="Major electoral shift with lasting national political impact."
- Title: "COP31 kicks off as planet faces imminent overshoot of 1.5°C climate target" \
→ geo_scope=global, places=[], theme_slugs=["climate"], story_label="COP31 Climate Summit", \
impact_tier=notable, impact_rationale="Ongoing climate diplomacy of broad interest."
- Title: "He spent a year on 'Mars': NASA science officer emerges from mock mission" \
→ geo_scope=global, places=[], theme_slugs=[], story_label="NASA Mars Mock Mission", \
impact_tier=ephemeral, impact_rationale="Human-interest science feature, short half-life."
- Title: "UK social media ban expansion for under-16s could cover YouTube Kids" \
→ geo_scope=national, \
places=[{"query":"United Kingdom","mention_basis":"explicit","country_hint":"GB"}], \
theme_slugs=["media","politics"], story_label="UK Under-16 Social Media Ban", \
impact_tier=notable, impact_rationale="National policy change with durable media effects."
- Title: "House votes to effectively end the impeachment effort against Pete Hegseth" \
→ geo_scope=global, places=[], theme_slugs=["politics"], \
story_label="Pete Hegseth Impeachment", \
impact_tier=notable, impact_rationale="Significant US political process development."
- Title: "Global stock markets mixed as investors await central bank signals" \
→ geo_scope=global, places=[], theme_slugs=["markets"], story_label="", \
impact_tier=ephemeral, impact_rationale="Routine market chatter without structural change."
"""


def extract_place_and_themes(
    *,
    title: str,
    summary: str,
    themes: list[dict[str, str]] | list[str],
    feed_language: str = "",
) -> dict[str, Any]:
    """Return geo_scope, place candidate, themes, story_label, and impact tier.

    ``themes`` may be ``[{"slug","label"}, ...]`` or bare slug strings.
    Failures raise; callers may catch and fall back to global / no themes.

    Place candidates are emitted only for explicit mentions with a country hint.
    ``geo_confidence`` is not set here — the attach policy sets it after geocode.
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
    lang = (feed_language or "").strip().lower()
    lang_line = f"Feed language hint: {lang}\n\n" if lang and lang != "und" else ""
    user = (
        f"{lang_line}"
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
    country_hint = ""
    mention_basis: MentionBasis = "none"
    places = data.get("places") or []
    if isinstance(places, list) and places:
        first = places[0] if isinstance(places[0], dict) else {}
        place_query = str(first.get("query") or "").strip()
        raw_basis = str(first.get("mention_basis") or "none").strip().lower()
        mention_basis = "explicit" if raw_basis == "explicit" else "none"
        country_hint = _normalize_country_hint(str(first.get("country_hint") or ""))

    if mention_basis != "explicit" or not place_query or not country_hint:
        place_query = ""
        country_hint = ""
        mention_basis = "none"

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

    impact_tier = _normalize_impact_tier(str(data.get("impact_tier") or ""))
    impact_rationale = str(data.get("impact_rationale") or "").strip()[:160]

    return {
        "geo_scope": scope,
        "place_query": place_query,
        "country_hint": country_hint,
        "mention_basis": mention_basis,
        "theme_slugs": themes_out,
        "suggested_themes": suggestions,
        "story_label": story_label,
        "impact_tier": impact_tier,
        "impact_rationale": impact_rationale,
    }
