from django.test import TestCase

from news.models import GeoLevel
from news.services.places import (
    SCORE_ADMIN1,
    SCORE_COUNTRY,
    SCORE_LOCALITY_EXACT,
    SCORE_LOCALITY_NEAR,
    SCORE_UPWARD_COUNTRY,
    haversine_km,
    place_dict_match,
)


class PlacesMatchTests(TestCase):
    def test_global_article_no_boost(self) -> None:
        score = place_dict_match(
            {"geo_level": GeoLevel.GLOBAL, "country_code": "de"},
            {"geo_level": GeoLevel.LOCALITY, "country_code": "de", "locality": "Cologne"},
        )
        self.assertEqual(score, 0.0)

    def test_country_article_matches_city_loi(self) -> None:
        score = place_dict_match(
            {
                "geo_level": GeoLevel.COUNTRY,
                "country_code": "de",
                "place_label": "Germany",
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.94,
                "longitude": 6.96,
            },
        )
        self.assertEqual(score, SCORE_COUNTRY)

    def test_admin1_article_matches_same_region(self) -> None:
        score = place_dict_match(
            {
                "geo_level": GeoLevel.ADMIN1,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
            },
        )
        self.assertEqual(score, SCORE_ADMIN1)

    def test_locality_exact(self) -> None:
        score = place_dict_match(
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.94,
                "longitude": 6.96,
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.94,
                "longitude": 6.96,
            },
        )
        self.assertEqual(score, SCORE_LOCALITY_EXACT)

    def test_locality_near_distance(self) -> None:
        # Bonn ≈ 25 km from Cologne — within 50 km peer radius.
        score = place_dict_match(
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.9375,
                "longitude": 6.9603,
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Bonn",
                "latitude": 50.7374,
                "longitude": 7.0982,
            },
        )
        self.assertEqual(score, SCORE_LOCALITY_NEAR)
        self.assertLess(
            haversine_km(50.9375, 6.9603, 50.7374, 7.0982),
            50.0,
        )

    def test_upward_country_loi_vs_city_article(self) -> None:
        score = place_dict_match(
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.94,
                "longitude": 6.96,
            },
            {
                "geo_level": GeoLevel.COUNTRY,
                "country_code": "de",
                "admin1": "",
                "locality": "",
            },
        )
        self.assertEqual(score, SCORE_UPWARD_COUNTRY)

    def test_does_not_match_other_country(self) -> None:
        score = place_dict_match(
            {
                "geo_level": GeoLevel.COUNTRY,
                "country_code": "de",
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "fr",
                "locality": "Paris",
            },
        )
        self.assertEqual(score, 0.0)

    def test_country_centroid_not_used_for_distant_cities(self) -> None:
        # Munich vs Cologne (~450 km): different localities, same country —
        # no distance match without shared locality / near peer.
        score = place_dict_match(
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "Bavaria",
                "locality": "Munich",
                "latitude": 48.137,
                "longitude": 11.575,
            },
            {
                "geo_level": GeoLevel.LOCALITY,
                "country_code": "de",
                "admin1": "North Rhine-Westphalia",
                "locality": "Cologne",
                "latitude": 50.938,
                "longitude": 6.960,
            },
        )
        self.assertEqual(score, 0.0)
