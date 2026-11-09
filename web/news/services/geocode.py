"""Coarse geocoding via OpenStreetMap Nominatim (no API key)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_USER_AGENT = "NoiseToSignal/0.1 (https://github.com/KjeldSchmidt/noise-to-signal; news aggregator)"
_TIMEOUT_S = 8
_DEFAULT_LANG = "en"


def _normalize_lang(lang: str | None) -> str:
    """Build a Nominatim accept-language preference list ending in English."""
    raw = (lang or "").strip() or _DEFAULT_LANG
    parts: list[str] = []
    for token in raw.replace(";", ",").split(","):
        tag = token.strip().split(";")[0].strip()
        if tag and tag not in parts:
            parts.append(tag)
    if _DEFAULT_LANG not in parts and not any(
        p.lower().startswith("en") for p in parts
    ):
        parts.append(_DEFAULT_LANG)
    return ",".join(parts) or _DEFAULT_LANG


def _nominatim_get(path: str, params: dict[str, str]) -> Any | None:
    query = urllib.parse.urlencode(params)
    url = f"https://nominatim.openstreetmap.org/{path}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        logger.exception("Nominatim %s failed (%s)", path, params)
        return None


def _locality_from_address(address: dict[str, Any]) -> str:
    return (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or address.get("state_district")
        or ""
    )


def _admin1_from_address(address: dict[str, Any]) -> str:
    return address.get("state") or address.get("region") or ""


def hierarchy_from_address(
    address: dict[str, Any] | None,
    display_name: str = "",
    *,
    scope_hint: str | None = None,
) -> dict[str, Any]:
    """Normalize Nominatim address details into country/admin1/locality + geo_level."""
    address = address or {}
    country_code = (address.get("country_code") or "").strip().lower()[:2]
    admin1 = (_admin1_from_address(address) or "").strip()[:120]
    locality = (_locality_from_address(address) or "").strip()[:120]
    country_name = (address.get("country") or "").strip()

    parts = [p for p in (locality, admin1, country_name) if p]
    deduped: list[str] = []
    for part in parts:
        if not deduped or deduped[-1].casefold() != part.casefold():
            deduped.append(part)
    label = ", ".join(deduped)[:200] if deduped else ""
    if not label:
        bits = [b.strip() for b in (display_name or "").split(",") if b.strip()]
        label = ", ".join(bits[:3])[:200]

    hint = (scope_hint or "").strip().lower()
    if hint in {"global"} or not country_code:
        geo_level = "global"
    elif hint in {"national", "country"} or (country_code and not admin1 and not locality):
        geo_level = "country"
    elif hint in {"regional", "admin1"} or (admin1 and not locality):
        geo_level = "admin1"
    elif locality:
        geo_level = "locality"
    elif admin1:
        geo_level = "admin1"
    elif country_code:
        geo_level = "country"
    else:
        geo_level = "global"

    if geo_level == "global":
        country_code = ""
        admin1 = ""
        locality = ""

    return {
        "label": label,
        "country_code": country_code,
        "admin1": admin1,
        "locality": locality,
        "geo_level": geo_level,
    }


def _label_from_address(address: dict[str, Any], display_name: str = "") -> str | None:
    hier = hierarchy_from_address(address, display_name)
    return hier["label"] or None


def reverse_geocode_label(
    latitude: float, longitude: float, *, lang: str | None = None
) -> str | None:
    """Return a short place name (city/region/country) or None on failure."""
    place = reverse_geocode_place(latitude, longitude, lang=lang)
    return place["label"] if place else None


def reverse_geocode_place(
    latitude: float, longitude: float, *, lang: str | None = None
) -> dict[str, Any] | None:
    """Reverse-geocode to hierarchical place fields + coords."""
    payload = _nominatim_get(
        "reverse",
        {
            "lat": f"{latitude:.5f}",
            "lon": f"{longitude:.5f}",
            "format": "jsonv2",
            "zoom": "10",
            "addressdetails": "1",
            "accept-language": _normalize_lang(lang),
        },
    )
    if not isinstance(payload, dict):
        return None
    hier = hierarchy_from_address(
        payload.get("address") or {}, payload.get("display_name") or ""
    )
    if not hier["label"] and not hier["country_code"]:
        return None
    return {
        **hier,
        "latitude": latitude,
        "longitude": longitude,
    }


def search_places(
    query: str, *, limit: int = 5, lang: str | None = None, scope_hint: str | None = None
) -> list[dict[str, Any]]:
    """Forward-geocode a place query into labeled hierarchy + lat/lng hits."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    payload = _nominatim_get(
        "search",
        {
            "q": q,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": str(max(1, min(limit, 8))),
            "accept-language": _normalize_lang(lang),
        },
    )
    if not isinstance(payload, list):
        return []

    results: list[dict[str, Any]] = []
    for hit in payload:
        try:
            lat = float(hit["lat"])
            lng = float(hit["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        hier = hierarchy_from_address(
            hit.get("address") or {},
            hit.get("display_name") or "",
            scope_hint=scope_hint,
        )
        if not hier["label"] and not hier["country_code"]:
            continue
        results.append(
            {
                **hier,
                "latitude": lat,
                "longitude": lng,
            }
        )
    return results
