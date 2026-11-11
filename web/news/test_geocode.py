"""Unit tests for Nominatim search metadata passthrough."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from news.services.geocode import search_places


class GeocodeSearchMetadataTests(SimpleTestCase):
    @patch("news.services.geocode._nominatim_get")
    def test_search_places_passes_osm_metadata(self, mock_get) -> None:
        mock_get.return_value = [
            {
                "lat": "50.93836",
                "lon": "6.95997",
                "display_name": "Cologne, NRW, Germany",
                "class": "place",
                "type": "city",
                "importance": 0.72,
                "address": {
                    "city": "Cologne",
                    "state": "North Rhine-Westphalia",
                    "country": "Germany",
                    "country_code": "de",
                },
            }
        ]
        hits = search_places("Cologne, Germany", limit=5, scope_hint="local")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit["osm_class"], "place")
        self.assertEqual(hit["osm_type"], "city")
        self.assertEqual(hit["importance"], 0.72)
        self.assertEqual(hit["country_code"], "de")
        self.assertEqual(hit["locality"], "Cologne")

    @patch("news.services.geocode._nominatim_get")
    def test_search_places_reads_jsonv2_category(self, mock_get) -> None:
        mock_get.return_value = [
            {
                "lat": "40.0",
                "lon": "-3.0",
                "display_name": "Spain",
                "category": "boundary",
                "type": "administrative",
                "importance": 0.9,
                "address": {
                    "country": "Spain",
                    "country_code": "es",
                },
            }
        ]
        hits = search_places("Spain", limit=5, scope_hint="national")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["osm_class"], "boundary")
        self.assertEqual(hits[0]["osm_type"], "administrative")
        self.assertEqual(hits[0]["importance"], 0.9)
        self.assertEqual(hits[0]["geo_level"], "country")
