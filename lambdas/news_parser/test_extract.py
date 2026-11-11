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
            places=[{"query": "Germany", "confidence": 0.9}],
            theme_slugs=["climate", "energy"],
            suggested_themes=["not-a-real-theme"],
            story_label="",
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
        self.assertEqual(out["theme_slugs"], ["climate", "energy"])
        self.assertEqual(out["suggested_themes"], ["not-a-real-theme"])
        self.assertEqual(out["geo_confidence"], 0.9)

    @patch("extract.get_extract_model")
    def test_extract_low_confidence_clears_place(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["climate"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="local",
            places=[{"query": "Somewhere", "confidence": 0.2}],
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
        self.assertIsNone(out["geo_confidence"])

    @patch("extract.get_extract_model")
    def test_global_scope_keeps_high_confidence_place(self, mock_get_model: MagicMock) -> None:
        schema = extract_mod._build_extract_model(["disaster", "politics"])
        structured = MagicMock()
        structured.invoke.return_value = schema(
            geo_scope="global",
            places=[{"query": "Spain", "confidence": 0.9}],
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
        self.assertEqual(out["geo_confidence"], 0.9)
        self.assertEqual(out["story_label"], "Spanish Rail Crash")
        self.assertEqual(out["theme_slugs"], ["disaster"])

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
