"""Structured geo/theme extraction via Bedrock Converse."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import boto3

logger = logging.getLogger(__name__)

EXTRACT_MODEL_ID = os.environ.get(
    "BEDROCK_EXTRACT_MODEL_ID", "amazon.nova-micro-v1:0"
)
_PLACE_CONFIDENCE_MIN = 0.55


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model response")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model response")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON payload is not an object")
    return data


def extract_place_and_themes(
    *,
    title: str,
    summary: str,
    theme_slugs: list[str],
) -> dict[str, Any]:
    """Return geo_scope, optional place query, confidence, and theme_slugs.

    Failures raise; callers may catch and fall back to global / no themes.
    """
    allowed = sorted({s.strip() for s in theme_slugs if s.strip()})
    system = (
        "You classify news articles for a personal news filter. "
        "Respond with ONLY a JSON object (no markdown) using this schema:\n"
        '{"geo_scope":"local|regional|national|global",'
        '"places":[{"query":"string","confidence":0.0}],'
        '"theme_slugs":["slug"]}\n'
        "geo_scope=global when there is no strong geographic focus. "
        "places may be empty. theme_slugs must be chosen ONLY from the allowed "
        "list (0 or more). Use English place queries suitable for OpenStreetMap "
        "Nominatim (e.g. 'Cologne, Germany' or 'Germany')."
    )
    user = (
        f"Allowed theme_slugs: {json.dumps(allowed)}\n\n"
        f"Title: {title}\n\nSummary: {summary[:1500]}"
    )
    client = boto3.client("bedrock-runtime", region_name=_bedrock_region())
    response = client.converse(
        modelId=EXTRACT_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.0},
    )
    parts = response.get("output", {}).get("message", {}).get("content") or []
    text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    data = _parse_json_object(text)

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

    if scope == "global" or confidence < _PLACE_CONFIDENCE_MIN:
        place_query = ""
        confidence = 0.0
        scope = "global" if not place_query else scope

    allowed_set = set(allowed)
    themes: list[str] = []
    for slug in data.get("theme_slugs") or []:
        s = str(slug).strip()
        if s in allowed_set and s not in themes:
            themes.append(s)

    return {
        "geo_scope": scope,
        "place_query": place_query,
        "geo_confidence": confidence if place_query else None,
        "theme_slugs": themes,
    }
