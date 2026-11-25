"""Hierarchical place matching — re-export shared n2s_api helpers."""

from __future__ import annotations

from n2s_api.places import (
    LOCALITY_RADIUS_KM,
    SCORE_ADMIN1,
    SCORE_COUNTRY,
    SCORE_LOCALITY_EXACT,
    SCORE_LOCALITY_NEAR,
    SCORE_UPWARD_COUNTRY,
    PlaceLike,
    haversine_km,
    place_dict_match,
    places_match,
)

__all__ = [
    "LOCALITY_RADIUS_KM",
    "SCORE_ADMIN1",
    "SCORE_COUNTRY",
    "SCORE_LOCALITY_EXACT",
    "SCORE_LOCALITY_NEAR",
    "SCORE_UPWARD_COUNTRY",
    "PlaceLike",
    "haversine_km",
    "place_dict_match",
    "places_match",
]
