"""Unit tests for place/theme extraction (mocked LangChain structured model)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import extract as extract_mod
from extract import PlaceMention, PlaceThemeExtract


class ExtractTests(unittest.TestCase):
    @patch("extract.get_extract_model")
    def test_extract_filters_unknown_themes(self, mock_get_model: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = PlaceThemeExtract(
            geo_scope="national",
            places=[PlaceMention(query="Germany", confidence=0.9)],
            theme_slugs=["climate", "not-a-real-theme", "energy"],
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Floods hit the Rhine",
            summary="Authorities warn of rising water levels in western Germany.",
            theme_slugs=["climate", "energy", "markets"],
        )
        self.assertEqual(out["geo_scope"], "national")
        self.assertEqual(out["place_query"], "Germany")
        self.assertEqual(out["theme_slugs"], ["climate", "energy"])
        self.assertEqual(out["geo_confidence"], 0.9)

    @patch("extract.get_extract_model")
    def test_extract_low_confidence_clears_place(self, mock_get_model: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = PlaceThemeExtract(
            geo_scope="local",
            places=[PlaceMention(query="Somewhere", confidence=0.2)],
            theme_slugs=[],
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Vague news",
            summary="Things happened.",
            theme_slugs=["climate"],
        )
        self.assertEqual(out["geo_scope"], "local")
        self.assertEqual(out["place_query"], "")
        self.assertIsNone(out["geo_confidence"])

    @patch("extract.get_extract_model")
    def test_global_scope_keeps_high_confidence_place(self, mock_get_model: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = PlaceThemeExtract(
            geo_scope="global",
            places=[PlaceMention(query="Spain", confidence=0.9)],
            theme_slugs=[],
            story_label="Spanish Rail Crash",
        )
        mock_get_model.return_value.with_structured_output.return_value = structured

        out = extract_mod.extract_place_and_themes(
            title="Spain's king and queen attend memorial service for rail crash victims",
            summary="Leaders gathered in Spain after the deadly crash.",
            theme_slugs=["politics"],
        )
        self.assertEqual(out["geo_scope"], "global")
        self.assertEqual(out["place_query"], "Spain")
        self.assertEqual(out["geo_confidence"], 0.9)
        self.assertEqual(out["story_label"], "Spanish Rail Crash")


if __name__ == "__main__":
    unittest.main()
