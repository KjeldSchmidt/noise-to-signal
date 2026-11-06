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
    # Allow "de-DE,de;q=0.9" style — take primary tags only.
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


def _label_from_address(address: dict[str, Any], display_name: str = "") -> str | None:
    locality = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or address.get("state_district")
    )
    region = address.get("state") or address.get("region")
    country = address.get("country")

    parts = [p for p in (locality, region, country) if p]
    deduped: list[str] = []
    for part in parts:
        if not deduped or deduped[-1].casefold() != part.casefold():
            deduped.append(part)
    if deduped:
        return ", ".join(deduped)[:200]

    display = (display_name or "").strip()
    if display:
        bits = [b.strip() for b in display.split(",") if b.strip()]
        return ", ".join(bits[:3])[:200]
    return None


def reverse_geocode_label(
    latitude: float, longitude: float, *, lang: str | None = None
) -> str | None:
    """Return a short place name (city/region/country) or None on failure."""
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
    return _label_from_address(payload.get("address") or {}, payload.get("display_name") or "")


def search_places(
    query: str, *, limit: int = 5, lang: str | None = None
) -> list[dict[str, Any]]:
    """Forward-geocode a place query into labeled lat/lng hits."""
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
        label = _label_from_address(hit.get("address") or {}, hit.get("display_name") or "")
        if not label:
            continue
        results.append({"label": label, "latitude": lat, "longitude": lng})
    return results
