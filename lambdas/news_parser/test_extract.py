"""Unit tests for place/theme JSON parsing (no Bedrock calls)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import extract as extract_mod


class ExtractTests(unittest.TestCase):
    def test_parse_json_object_direct(self) -> None:
        data = extract_mod._parse_json_object(
            '{"geo_scope":"national","places":[],"theme_slugs":["climate"]}'
        )
        self.assertEqual(data["geo_scope"], "national")
        self.assertEqual(data["theme_slugs"], ["climate"])

    def test_parse_json_object_fenced(self) -> None:
        data = extract_mod._parse_json_object(
            'Here you go:\n```json\n{"geo_scope":"global","places":[],"theme_slugs":[]}\n```'
        )
        self.assertEqual(data["geo_scope"], "global")

    @patch("extract.boto3.client")
    def test_extract_filters_unknown_themes(self, mock_client: MagicMock) -> None:
        mock_client.return_value.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": (
                                '{"geo_scope":"national",'
                                '"places":[{"query":"Germany","confidence":0.9}],'
                                '"theme_slugs":["climate","not-a-real-theme","energy"]}'
                            )
                        }
                    ]
                }
            }
        }
        out = extract_mod.extract_place_and_themes(
            title="Floods hit the Rhine",
            summary="Authorities warn of rising water levels in western Germany.",
            theme_slugs=["climate", "energy", "markets"],
        )
        self.assertEqual(out["geo_scope"], "national")
        self.assertEqual(out["place_query"], "Germany")
        self.assertEqual(out["theme_slugs"], ["climate", "energy"])
        self.assertEqual(out["geo_confidence"], 0.9)

    @patch("extract.boto3.client")
    def test_extract_low_confidence_becomes_global(
        self, mock_client: MagicMock
    ) -> None:
        mock_client.return_value.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": (
                                '{"geo_scope":"local",'
                                '"places":[{"query":"Somewhere","confidence":0.2}],'
                                '"theme_slugs":[]}'
                            )
                        }
                    ]
                }
            }
        }
        out = extract_mod.extract_place_and_themes(
            title="Vague news",
            summary="Things happened.",
            theme_slugs=["climate"],
        )
        self.assertEqual(out["geo_scope"], "global")
        self.assertEqual(out["place_query"], "")
        self.assertIsNone(out["geo_confidence"])


if __name__ == "__main__":
    unittest.main()
