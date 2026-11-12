from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from n2s_api import Feed as FeedDTO
from n2s_api import FeedListResponse

from news.models import Feed, FeedMute, Subscription, UserContentLanguage
from news.services.feeds import enabled_feed_ids, feed_should_poll
from news.views import _resolve_custom_feed

UserModel = cast(Any, get_user_model())


class EnabledFeedIdsTests(TestCase):
    def setUp(self) -> None:
        self.user = UserModel.objects.create_user(username="reader", password="x")
        UserContentLanguage.objects.create(user=self.user, language="en")
        self.en = Feed.objects.create(
            title="BBC",
            url="https://example.com/en.xml",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.de = Feed.objects.create(
            title="Tagesschau",
            url="https://example.com/de.xml",
            kind=Feed.SourceKind.CURATED,
            language="de",
        )
        self.custom = Feed.objects.create(
            title="Niche",
            url="https://example.com/custom.xml",
            kind=Feed.SourceKind.CUSTOM,
            language="und",
            owner=self.user,
        )

    def test_default_en_excludes_other_catalog_languages(self) -> None:
        ids = enabled_feed_ids(self.user)
        self.assertIn(self.en.id, ids)
        self.assertNotIn(self.de.id, ids)
        self.assertNotIn(self.custom.id, ids)

    def test_enabling_de_includes_german_catalog(self) -> None:
        UserContentLanguage.objects.create(user=self.user, language="de")
        ids = enabled_feed_ids(self.user)
        self.assertIn(self.en.id, ids)
        self.assertIn(self.de.id, ids)

    def test_mute_removes_catalog_feed(self) -> None:
        FeedMute.objects.create(user=self.user, feed=self.en)
        self.assertNotIn(self.en.id, enabled_feed_ids(self.user))

    def test_subscription_includes_unknown_language_custom(self) -> None:
        Subscription.objects.create(user=self.user, feed=self.custom)
        self.assertIn(self.custom.id, enabled_feed_ids(self.user))

    def test_subscription_respects_known_custom_language(self) -> None:
        fr_custom = Feed.objects.create(
            title="FR custom",
            url="https://example.com/fr-custom.xml",
            kind=Feed.SourceKind.CUSTOM,
            language="fr",
        )
        Subscription.objects.create(user=self.user, feed=fr_custom)
        self.assertNotIn(fr_custom.id, enabled_feed_ids(self.user))
        UserContentLanguage.objects.create(user=self.user, language="fr")
        self.assertIn(fr_custom.id, enabled_feed_ids(self.user))


class ResolveCustomFeedTests(TestCase):
    def setUp(self) -> None:
        self.user_a = UserModel.objects.create_user(username="a", password="x")
        self.user_b = UserModel.objects.create_user(username="b", password="x")
        self.catalog = Feed.objects.create(
            title="BBC",
            url="https://example.com/bbc.xml",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )

    def test_new_url_creates_feed_and_subscription(self) -> None:
        feed, msg = _resolve_custom_feed(
            self.user_a,
            {
                "title": "Mine",
                "url": "https://example.com/new.xml",
                "site_url": "",
                "description": "",
                "category": "Custom",
            },
        )
        self.assertEqual(feed.kind, Feed.SourceKind.CUSTOM)
        self.assertEqual(feed.language, "und")
        self.assertTrue(Subscription.objects.filter(user=self.user_a, feed=feed).exists())
        self.assertIn("Added", msg)

    def test_existing_custom_subscribes_second_user(self) -> None:
        feed, _ = _resolve_custom_feed(
            self.user_a,
            {
                "title": "Shared",
                "url": "https://example.com/shared.xml",
                "site_url": "",
                "description": "",
                "category": "Custom",
            },
        )
        before = Feed.objects.filter(url="https://example.com/shared.xml").count()
        same, msg = _resolve_custom_feed(
            self.user_b,
            {
                "title": "Ignored",
                "url": "https://example.com/shared.xml",
                "site_url": "",
                "description": "",
                "category": "Custom",
            },
        )
        self.assertEqual(before, 1)
        self.assertEqual(same.id, feed.id)
        self.assertTrue(Subscription.objects.filter(user=self.user_b, feed=feed).exists())
        self.assertIn("Subscribed", msg)

    def test_existing_catalog_unmutes(self) -> None:
        FeedMute.objects.create(user=self.user_a, feed=self.catalog)
        feed, msg = _resolve_custom_feed(
            self.user_a,
            {
                "title": "ignored",
                "url": self.catalog.url,
                "site_url": "",
                "description": "",
                "category": "Custom",
            },
        )
        self.assertEqual(feed.id, self.catalog.id)
        self.assertFalse(FeedMute.objects.filter(user=self.user_a, feed=self.catalog).exists())
        self.assertIn("catalog", msg)


class FeedShouldPollTests(TestCase):
    def test_catalog_active_polls(self) -> None:
        self.assertTrue(
            feed_should_poll(kind=Feed.SourceKind.CURATED, is_active=True, subscription_count=0)
        )

    def test_custom_requires_subscribers(self) -> None:
        self.assertFalse(
            feed_should_poll(kind=Feed.SourceKind.CUSTOM, is_active=True, subscription_count=0)
        )
        self.assertTrue(
            feed_should_poll(kind=Feed.SourceKind.CUSTOM, is_active=True, subscription_count=1)
        )


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class ListFeedsShouldPollApiTests(TestCase):
    def test_custom_without_subscribers_should_not_poll(self) -> None:
        Feed.objects.create(
            title="Orphan custom",
            url="https://example.com/orphan.xml",
            kind=Feed.SourceKind.CUSTOM,
            language="und",
            is_active=True,
        )
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        typed = FeedListResponse.model_validate(response.json())
        self.assertEqual(len(typed.feeds), 1)
        row: FeedDTO = typed.feeds[0]
        self.assertEqual(row.kind, Feed.SourceKind.CUSTOM)
        self.assertFalse(row.should_poll)
        self.assertEqual(row.language, "und")
