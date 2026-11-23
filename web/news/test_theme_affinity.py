"""Tests for theme affinity weights and bump helpers."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from news.models import Theme, UserThemeAffinity
from news.services.theme_affinity import affinity_weight, bump_theme_affinity

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    # django-stubs types User.objects as Manager[AbstractBaseUser] without create_user.
    return cast(Any, User.objects).create_user(**kwargs)


class ThemeAffinityWeightTests(TestCase):
    def test_log_damping(self) -> None:
        self.assertAlmostEqual(affinity_weight(0, 0), 0.0)
        self.assertGreater(affinity_weight(3, 0), affinity_weight(1, 0))
        self.assertLess(affinity_weight(0, 2), 0.0)
        # Extra counts matter less than the first.
        self.assertLess(
            affinity_weight(10, 0) - affinity_weight(9, 0),
            affinity_weight(2, 0) - affinity_weight(1, 0),
        )


class ThemeAffinityBumpTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="aff", password="x")
        self.theme, _ = Theme.objects.get_or_create(
            slug="affinity-test-sports",
            defaults={"label": "Sports", "sort_order": 1},
        )

    def test_bump_more_and_less(self) -> None:
        bump_theme_affinity(self.user, theme_slug="affinity-test-sports", direction="more")
        bump_theme_affinity(self.user, theme_slug="affinity-test-sports", direction="more")
        bump_theme_affinity(self.user, theme_slug="affinity-test-sports", direction="less")
        row = UserThemeAffinity.objects.get(user=self.user, theme=self.theme)
        self.assertEqual(row.more_count, 2)
        self.assertEqual(row.less_count, 1)

    def test_unknown_slug(self) -> None:
        self.assertIsNone(bump_theme_affinity(self.user, theme_slug="nope", direction="more"))


class ThemeAffinityEndpointTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="aff2", password="x")
        self.client = Client()
        self.client.force_login(self.user)

    def test_stored_preferences_empty(self) -> None:
        response = self.client.get("/settings/preferences/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["memories"], [])
        self.assertEqual(data["themes"], [])
