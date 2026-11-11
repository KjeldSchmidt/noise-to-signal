"""Deterministic keep/discard policy for geocoded article places."""

from __future__ import annotations

from dataclasses import dataclass

from n2s_api import GeocodePlace

# Below this, short single-token local queries are treated as weak homonyms.
_WEAK_LOCAL_IMPORTANCE_MAX = 0.35


@dataclass(frozen=True)
class AttachDecision:
    keep: bool
    hit: GeocodePlace | None
    reason: str


_PLACE_TYPES: frozenset[str] = frozenset(
    {
        "country",
        "state",
        "region",
        "province",
        "county",
        "city",
        "town",
        "village",
        "municipality",
        "hamlet",
        "suburb",
        "neighbourhood",
        "neighborhood",
        "borough",
        "district",
        "quarter",
        "island",
        "archipelago",
    }
)

_BOUNDARY_TYPES: frozenset[str] = frozenset({"administrative", "political"})


def is_place_like(hit: GeocodePlace) -> bool:
    """True for settlement / admin geography; false for POIs and amenities."""
    osm_class = (hit.osm_class or "").strip().lower()
    osm_type = (hit.osm_type or "").strip().lower()
    if osm_class in {"place", "boundary"}:
        if osm_class == "place" and osm_type in _PLACE_TYPES:
            return True
        if osm_class == "boundary" and osm_type in _BOUNDARY_TYPES:
            return True
        # Some Nominatim hits omit type detail but are still admin places.
        if osm_class == "place" and not osm_type:
            return True
        if osm_class == "boundary" and not osm_type:
            return True
        return False
    # Legacy / incomplete metadata: allow hierarchy-bearing hits through.
    if not osm_class and not osm_type:
        return bool(hit.country_code or hit.label)
    return False


def _country_code(hit: GeocodePlace) -> str:
    return (hit.country_code or "").strip().lower()[:2]


def _is_short_single_token_query(place_query: str) -> bool:
    q = (place_query or "").strip()
    if not q or "," in q:
        return False
    tokens = [t for t in q.split() if t]
    return len(tokens) == 1


def _scope_rank(hit: GeocodePlace, geo_scope: str) -> tuple[int, float]:
    """Higher is better for selecting among country-matched hits."""
    level = (hit.geo_level or "").strip().lower()
    osm_type = (hit.osm_type or "").strip().lower()
    importance = float(hit.importance) if hit.importance is not None else 0.0
    scope = (geo_scope or "").strip().lower()

    if scope == "national":
        if level == "country" or osm_type == "country":
            level_score = 3
        elif level == "admin1":
            level_score = 1
        else:
            level_score = 0
    elif scope == "regional":
        if level == "admin1" or osm_type in {"state", "region", "province"}:
            level_score = 3
        elif level == "country":
            level_score = 2
        else:
            level_score = 1
    else:  # local / global / unknown — prefer locality when present
        if level == "locality" or osm_type in {
            "city",
            "town",
            "village",
            "municipality",
            "hamlet",
            "suburb",
            "neighbourhood",
            "neighborhood",
            "borough",
        }:
            level_score = 3
        elif level == "admin1":
            level_score = 2
        elif level == "country":
            level_score = 1
        else:
            level_score = 0
    return (level_score, importance)


def decide_attach(
    *,
    place_query: str,
    country_hint: str,
    geo_scope: str,
    hits: list[GeocodePlace],
) -> AttachDecision:
    """Keep a geocode hit only when place-like, country-matched, and unambiguous."""
    hint = (country_hint or "").strip().lower()[:2]
    query = (place_query or "").strip()
    if not query or len(hint) != 2:
        return AttachDecision(False, None, "missing_query_or_country_hint")
    if not hits:
        return AttachDecision(False, None, "no_hits")

    place_like = [h for h in hits if is_place_like(h)]
    if not place_like:
        return AttachDecision(False, None, "no_place_like_hits")

    countries = {_country_code(h) for h in place_like if _country_code(h)}
    if len(countries) > 1 and hint not in countries:
        return AttachDecision(False, None, "ambiguous_countries_no_hint_match")

    matched = [h for h in place_like if _country_code(h) == hint]
    if not matched:
        return AttachDecision(False, None, "country_hint_mismatch")

    matched_sorted = sorted(
        matched,
        key=lambda h: _scope_rank(h, geo_scope),
        reverse=True,
    )
    chosen = matched_sorted[0]

    scope = (geo_scope or "").strip().lower()
    if scope == "local" and _is_short_single_token_query(query):
        importance = chosen.importance
        if importance is None or float(importance) < _WEAK_LOCAL_IMPORTANCE_MAX:
            return AttachDecision(False, None, "weak_local_homonym")

    # National scope: refuse to attach a village-level hit when a country-level
    # alternative exists; if only locality remains, still discard.
    if scope == "national":
        level = (chosen.geo_level or "").strip().lower()
        osm_type = (chosen.osm_type or "").strip().lower()
        if level != "country" and osm_type != "country":
            country_hits = [
                h
                for h in matched
                if (h.geo_level or "").strip().lower() == "country"
                or (h.osm_type or "").strip().lower() == "country"
            ]
            if country_hits:
                chosen = sorted(
                    country_hits,
                    key=lambda h: _scope_rank(h, geo_scope),
                    reverse=True,
                )[0]
            else:
                return AttachDecision(False, None, "national_scope_not_country")

    return AttachDecision(True, chosen, "ok")
