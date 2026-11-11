"""Unit tests for deterministic place attach policy."""

from __future__ import annotations

from n2s_api import GeocodePlace

from place_attach import decide_attach, is_place_like


def _hit(
    *,
    label: str,
    country_code: str = "",
    admin1: str = "",
    locality: str = "",
    geo_level: str = "locality",
    osm_class: str = "place",
    osm_type: str = "city",
    importance: float | None = 0.6,
    latitude: float = 0.0,
    longitude: float = 0.0,
) -> GeocodePlace:
    return GeocodePlace(
        label=label,
        latitude=latitude,
        longitude=longitude,
        country_code=country_code,
        admin1=admin1,
        locality=locality,
        geo_level=geo_level,
        osm_class=osm_class,
        osm_type=osm_type,
        importance=importance,
    )


def test_is_place_like_rejects_amenities() -> None:
    assert not is_place_like(
        _hit(label="Cafe", osm_class="amenity", osm_type="cafe", country_code="de")
    )
    assert is_place_like(
        _hit(label="Cologne", osm_class="place", osm_type="city", country_code="de")
    )
    assert is_place_like(
        _hit(
            label="Germany",
            osm_class="boundary",
            osm_type="administrative",
            geo_level="country",
            country_code="de",
        )
    )


def test_mars_like_weak_local_homonym_discards() -> None:
    decision = decide_attach(
        place_query="Mars",
        country_hint="FR",
        geo_scope="local",
        hits=[
            _hit(
                label="Mars, France",
                country_code="fr",
                locality="Mars",
                osm_type="village",
                importance=0.12,
            )
        ],
    )
    assert decision.keep is False
    assert decision.reason == "weak_local_homonym"


def test_country_hint_mismatch_discards() -> None:
    decision = decide_attach(
        place_query="Mars",
        country_hint="US",
        geo_scope="local",
        hits=[
            _hit(
                label="Mars, France",
                country_code="fr",
                locality="Mars",
                osm_type="village",
                importance=0.12,
            )
        ],
    )
    assert decision.keep is False
    assert decision.reason == "country_hint_mismatch"


def test_ambiguous_multi_country_without_matching_hint_discards() -> None:
    decision = decide_attach(
        place_query="Georgia",
        country_hint="XX",
        geo_scope="national",
        hits=[
            _hit(
                label="Georgia",
                country_code="ge",
                geo_level="country",
                osm_class="boundary",
                osm_type="administrative",
                importance=0.8,
            ),
            _hit(
                label="Georgia, USA",
                country_code="us",
                geo_level="admin1",
                osm_type="state",
                importance=0.7,
            ),
        ],
    )
    assert decision.keep is False
    assert decision.reason == "ambiguous_countries_no_hint_match"


def test_spain_national_keeps_country_hit() -> None:
    decision = decide_attach(
        place_query="Spain",
        country_hint="ES",
        geo_scope="national",
        hits=[
            _hit(
                label="Spain",
                country_code="es",
                geo_level="country",
                osm_class="boundary",
                osm_type="administrative",
                importance=0.9,
            ),
            _hit(
                label="Madrid, Spain",
                country_code="es",
                locality="Madrid",
                geo_level="locality",
                osm_type="city",
                importance=0.7,
            ),
        ],
    )
    assert decision.keep is True
    assert decision.hit is not None
    assert decision.hit.geo_level == "country"
    assert decision.reason == "ok"


def test_cologne_local_keeps_qualified_query() -> None:
    decision = decide_attach(
        place_query="Cologne, Germany",
        country_hint="DE",
        geo_scope="local",
        hits=[
            _hit(
                label="Cologne, North Rhine-Westphalia, Germany",
                country_code="de",
                admin1="North Rhine-Westphalia",
                locality="Cologne",
                geo_level="locality",
                osm_type="city",
                importance=0.72,
            )
        ],
    )
    assert decision.keep is True
    assert decision.hit is not None
    assert decision.hit.locality == "Cologne"


def test_national_scope_without_country_hit_discards_village() -> None:
    decision = decide_attach(
        place_query="Spain",
        country_hint="ES",
        geo_scope="national",
        hits=[
            _hit(
                label="Some village, Spain",
                country_code="es",
                locality="Some village",
                geo_level="locality",
                osm_type="village",
                importance=0.2,
            )
        ],
    )
    assert decision.keep is False
    assert decision.reason == "national_scope_not_country"


def test_no_place_like_hits_discards() -> None:
    decision = decide_attach(
        place_query="COP31",
        country_hint="DK",
        geo_scope="local",
        hits=[
            _hit(
                label="Some venue",
                country_code="dk",
                osm_class="amenity",
                osm_type="conference_centre",
                importance=0.4,
            )
        ],
    )
    assert decision.keep is False
    assert decision.reason == "no_place_like_hits"
