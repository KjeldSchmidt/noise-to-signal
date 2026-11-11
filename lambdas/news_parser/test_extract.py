"""Unit tests for place/theme extraction (mocked LangChain structured model)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import extract as extract_mod


class ExtractTests(unittest.TestCase):
    def setUp(self) -> None:
        extract_mod._structured_cache.clear()

    @patch("extract.get_extract_model")
    def test_extract_keeps_allowlisted_themes(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["climate", "energy", "markets", "sports"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="national",
            places=[
                {
                    "query": "Germany",
                    "mention_basis": "explicit",
                    "country_hint": "DE",
                }
            ],
            theme_slugs=["climate", "energy"],
            suggested_themes=["not-a-real-theme"],
            story_label="",
            impact_tier="notable",
            impact_rationale="Acute regional flooding with civic impact.",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Floods hit the Rhine",
            summary="Authorities warn of rising water levels in western Germany.",
            themes=[
                {"slug": "climate", "label": "Climate"},
                {"slug": "energy", "label": "Energy"},
                {"slug": "markets", "label": "Markets"},
                {"slug": "sports", "label": "Sports"},
            ],
        )
        self.assertEqual(out["geo_scope"], "national")
        self.assertEqual(out["place_query"], "Germany")
        self.assertEqual(out["country_hint"], "DE")
        self.assertEqual(out["mention_basis"], "explicit")
        self.assertEqual(out["theme_slugs"], ["climate", "energy"])
        self.assertEqual(out["suggested_themes"], ["not-a-real-theme"])
        self.assertEqual(out["impact_tier"], "notable")
        self.assertEqual(out["impact_rationale"], "Acute regional flooding with civic impact.")
        self.assertNotIn("geo_confidence", out)

    @patch("extract.get_extract_model")
    def test_extract_none_basis_clears_place(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["climate"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="local",
            places=[
                {
                    "query": "Somewhere",
                    "mention_basis": "none",
                    "country_hint": "US",
                }
            ],
            theme_slugs=[],
            suggested_themes=[],
            story_label="",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Vague news",
            summary="Things happened.",
            themes=["climate"],
        )
        self.assertEqual(out["geo_scope"], "local")
        self.assertEqual(out["place_query"], "")
        self.assertEqual(out["country_hint"], "")
        self.assertEqual(out["mention_basis"], "none")

    @patch("extract.get_extract_model")
    def test_extract_missing_country_hint_clears_place(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["climate"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="local",
            places=[
                {
                    "query": "Cologne",
                    "mention_basis": "explicit",
                    "country_hint": "",
                }
            ],
            theme_slugs=[],
            suggested_themes=[],
            story_label="",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Cologne floods",
            summary="Rhine rising.",
            themes=["climate"],
        )
        self.assertEqual(out["place_query"], "")
        self.assertEqual(out["mention_basis"], "none")

    @patch("extract.get_extract_model")
    def test_global_scope_keeps_explicit_place(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["disaster", "politics"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="global",
            places=[
                {
                    "query": "Spain",
                    "mention_basis": "explicit",
                    "country_hint": "es",
                }
            ],
            theme_slugs=["disaster"],
            suggested_themes=[],
            story_label="Spanish Rail Crash",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Spain's king and queen attend memorial service for rail crash victims",
            summary="Leaders gathered in Spain after the deadly crash.",
            themes=[
                {"slug": "disaster", "label": "Disaster"},
                {"slug": "politics", "label": "Politics"},
            ],
        )
        self.assertEqual(out["geo_scope"], "global")
        self.assertEqual(out["place_query"], "Spain")
        self.assertEqual(out["country_hint"], "ES")
        self.assertEqual(out["mention_basis"], "explicit")
        self.assertEqual(out["story_label"], "Spanish Rail Crash")
        self.assertEqual(out["theme_slugs"], ["disaster"])

    def test_schema_defaults_missing_geo_scope(self) -> None:
        """Nova sometimes omits geo_scope; default global must parse."""
        schema = extract_mod._build_extract_model(["markets"])
        parsed = schema.model_validate(
            {
                "places": [
                    {
                        "query": "",
                        "mention_basis": "none",
                        "country_hint": "",
                    }
                ],
                "theme_slugs": ["markets"],
                "suggested_themes": [],
            }
        )
        self.assertEqual(parsed.geo_scope, "global")
        self.assertEqual(parsed.impact_tier, "ephemeral")

    @patch("extract.get_extract_model")
    def test_extract_truncates_impact_rationale(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["markets"])
        structured = MagicMock()
        structured.invoke.return_value = schema.model_validate(
            {
                "geo_scope": "global",
                "places": [],
                "theme_slugs": ["markets"],
                "suggested_themes": [],
                "story_label": "",
                "impact_tier": "ephemeral",
                "impact_rationale": "x" * 200,
            }
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Markets mixed",
            summary="Investors wait.",
            themes=["markets"],
        )
        self.assertEqual(out["impact_tier"], "ephemeral")
        self.assertEqual(len(out["impact_rationale"]), 160)

    def test_normalize_impact_tier_falls_back(self) -> None:
        self.assertEqual(extract_mod._normalize_impact_tier("MAJOR"), "major")
        self.assertEqual(extract_mod._normalize_impact_tier("nope"), "ephemeral")
        self.assertEqual(extract_mod._normalize_impact_tier(""), "ephemeral")

    @patch("extract.get_extract_model")
    def test_suggested_themes_drop_allowlisted_dupes(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["sports", "conflict"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="global",
            places=[],
            theme_slugs=["sports", "conflict"],
            suggested_themes=["Sports", "war-crimes", "Conflict"],
            story_label="",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Vinicius message",
            summary="Footballer messages boy in Sudan war.",
            themes=["sports", "conflict"],
        )
        self.assertEqual(out["theme_slugs"], ["sports", "conflict"])
        self.assertEqual(out["suggested_themes"], ["war-crimes"])


if __name__ == "__main__":
    unittest.main()
