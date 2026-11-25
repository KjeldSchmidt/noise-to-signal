"""Hierarchical place matching between articles and locations of interest."""

from __future__ import annotations

import math
from typing import Any, Protocol

# Mirror web.news.models.GeoLevel values (keep package free of Django).
GEO_GLOBAL = "global"
GEO_COUNTRY = "country"
GEO_ADMIN1 = "admin1"
GEO_LOCALITY = "locality"

# City-level peers only — never use this against country/region centroids.
LOCALITY_RADIUS_KM = 50.0

# Relative boost strengths for ranking (0 = no match).
SCORE_LOCALITY_EXACT = 1.0
SCORE_LOCALITY_NEAR = 0.85
SCORE_ADMIN1 = 0.65
SCORE_COUNTRY = 0.4
SCORE_UPWARD_COUNTRY = 0.35  # user saved country, article is finer


class PlaceLike(Protocol):
    geo_level: str
    country_code: str
    admin1: str
    locality: str
    latitude: float | None
    longitude: float | None


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def places_match(article: PlaceLike, loi: PlaceLike) -> float:
    """Return a geo boost score in [0, 1] for article vs user location of interest.

    Uses admin containment first. Haversine only for locality-level peers.
    """
    a_level = (article.geo_level or GEO_GLOBAL).strip() or GEO_GLOBAL
    if a_level == GEO_GLOBAL:
        return 0.0

    a_cc = _norm(article.country_code)
    u_cc = _norm(loi.country_code)
    if not a_cc or not u_cc or a_cc != u_cc:
        return 0.0

    a_admin = _norm(article.admin1)
    u_admin = _norm(loi.admin1)
    a_loc = _norm(article.locality)
    u_loc = _norm(loi.locality)
    u_level = (loi.geo_level or "").strip() or (
        GEO_LOCALITY if u_loc else GEO_ADMIN1 if u_admin else GEO_COUNTRY
    )

    # Downward: article coarser than / equal country covers all LOIs in country.
    if a_level == GEO_COUNTRY:
        return SCORE_COUNTRY

    # Article region: match LOIs in that admin1, or country-only LOIs weakly.
    if a_level == GEO_ADMIN1:
        if a_admin and u_admin and a_admin == u_admin:
            return SCORE_ADMIN1
        if u_level == GEO_COUNTRY and not u_admin and not u_loc:
            return SCORE_UPWARD_COUNTRY
        return 0.0

    # Article locality.
    if a_level == GEO_LOCALITY:
        if a_loc and u_loc and a_loc == u_loc:
            return SCORE_LOCALITY_EXACT
        if (
            article.latitude is not None
            and article.longitude is not None
            and loi.latitude is not None
            and loi.longitude is not None
            and (not u_admin or not a_admin or a_admin == u_admin)
        ):
            dist = haversine_km(
                float(article.latitude),
                float(article.longitude),
                float(loi.latitude),
                float(loi.longitude),
            )
            if dist <= LOCALITY_RADIUS_KM:
                return SCORE_LOCALITY_NEAR
        # Upward: user only cares about country/region containing this city.
        if u_level == GEO_COUNTRY and not u_loc:
            return SCORE_UPWARD_COUNTRY
        if u_level == GEO_ADMIN1 and a_admin and u_admin and a_admin == u_admin:
            return SCORE_UPWARD_COUNTRY
        return 0.0

    return 0.0


def place_dict_match(article: dict[str, Any], loi: dict[str, Any]) -> float:
    """Dict-friendly wrapper for tests / API payloads."""

    class _P:
        def __init__(self, d: dict[str, Any]) -> None:
            self.geo_level = str(d.get("geo_level") or GEO_GLOBAL)
            self.country_code = str(d.get("country_code") or "")
            self.admin1 = str(d.get("admin1") or "")
            self.locality = str(d.get("locality") or "")
            lat = d.get("latitude")
            lon = d.get("longitude")
            self.latitude = float(lat) if lat is not None else None
            self.longitude = float(lon) if lon is not None else None

    return places_match(_P(article), _P(loi))
