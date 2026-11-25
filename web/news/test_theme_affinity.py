"""Tests for theme affinity weights and vote helpers."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from news.models import Article, Feed, Theme, UserThemeAffinity
from news.services.theme_affinity import affinity_weight, apply_theme_affinity_vote

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


class ThemeAffinityVoteTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="aff", password="x")
        self.theme, _ = Theme.objects.get_or_create(
            slug="affinity-test-sports",
            defaults={"label": "Sports", "sort_order": 1},
        )

    def test_flip_sequence_matches_final_vote(self) -> None:
        slug = "affinity-test-sports"
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="more", previous="neutral")
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="less", previous="more")
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="more", previous="less")
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="less", previous="more")
        flipped = UserThemeAffinity.objects.get(user=self.user, theme=self.theme)

        other = _create_user(username="aff-once", password="x")
        apply_theme_affinity_vote(other, theme_slug=slug, direction="less", previous="neutral")
        once = UserThemeAffinity.objects.get(user=other, theme=self.theme)

        self.assertEqual(flipped.more_count, once.more_count)
        self.assertEqual(flipped.less_count, once.less_count)
        self.assertEqual(flipped.more_count, 0)
        self.assertEqual(flipped.less_count, 1)

    def test_same_direction_is_noop(self) -> None:
        slug = "affinity-test-sports"
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="more", previous="neutral")
        apply_theme_affinity_vote(self.user, theme_slug=slug, direction="more", previous="more")
        row = UserThemeAffinity.objects.get(user=self.user, theme=self.theme)
        self.assertEqual(row.more_count, 1)
        self.assertEqual(row.less_count, 0)

    def test_unknown_previous_raises(self) -> None:
        with self.assertRaises(ValueError):
            apply_theme_affinity_vote(
                self.user,
                theme_slug="affinity-test-sports",
                direction="more",
                previous=cast(Any, "sideways"),
            )

    def test_unknown_slug(self) -> None:
        self.assertIsNone(
            apply_theme_affinity_vote(
                self.user, theme_slug="nope", direction="more", previous="neutral"
            )
        )


class ThemeAffinityEndpointTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="aff2", password="x")
        self.client = Client()
        self.client.force_login(self.user)
        self.theme, _ = Theme.objects.get_or_create(
            slug="affinity-endpoint-tech",
            defaults={"label": "Tech", "sort_order": 2},
        )
        self.feed = Feed.objects.create(
            title="Affinity Feed",
            url="https://example.com/affinity-feed.xml",
            kind=Feed.SourceKind.CURATED,
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Affinity article",
            url="https://example.com/affinity-article",
            published_at=timezone.now(),
        )
        self.article.themes.add(self.theme)
        self.url = reverse("theme_affinity", args=[self.article.id])

    def test_stored_preferences_empty(self) -> None:
        response = self.client.get("/settings/preferences/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["memories"], [])
        self.assertEqual(data["themes"], [])

    def test_post_vote_json_with_previous(self) -> None:
        response = self.client.post(
            self.url,
            {"theme": self.theme.slug, "direction": "more", "previous": "neutral"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["direction"], "more")
        self.assertEqual(data["previous"], "neutral")
        self.assertEqual(data["more_count"], 1)
        self.assertEqual(data["less_count"], 0)
        self.assertIn("More", data["message"])

        flip = self.client.post(
            self.url,
            {"theme": self.theme.slug, "direction": "less", "previous": "more"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(flip.status_code, 200)
        flip_data = flip.json()
        self.assertEqual(flip_data["more_count"], 0)
        self.assertEqual(flip_data["less_count"], 1)

    def test_post_rejects_bad_previous(self) -> None:
        response = self.client.post(
            self.url,
            {"theme": self.theme.slug, "direction": "more", "previous": "sideways"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
