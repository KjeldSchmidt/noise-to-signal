from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from n2s_api import (
    Feed as FeedDTO,
)
from n2s_api import (
    FeedItem,
    FeedItemIngestRequest,
    FeedListResponse,
)

from news.models import Article, Feed, Theme, ThemeSuggestion


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class InternalFeedsApiTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="Internal Feeds Test",
            url="https://example.com/internal-feeds-test.xml",
            site_url="https://example.com/",
            category="World",
            kind=Feed.SourceKind.CURATED,
        )

    def test_list_feeds_requires_token(self) -> None:
        response = self.client.get("/api/internal/feeds/")
        self.assertEqual(response.status_code, 401)

    def test_list_feeds_rejects_bad_token(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer wrong"},
        )
        self.assertEqual(response.status_code, 401)

    def test_list_feeds_with_bearer_token(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        typed = FeedListResponse.model_validate(response.json())
        by_id = {row.id: row for row in typed.feeds}
        self.assertIn(self.feed.id, by_id)
        row = by_id[self.feed.id]
        self.assertEqual(row.url, self.feed.url)
        self.assertTrue(row.is_active)
        expected = FeedDTO(
            id=self.feed.id,
            title=self.feed.title,
            url=self.feed.url,
            site_url=self.feed.site_url,
            description=self.feed.description,
            category=self.feed.category,
            kind=self.feed.kind,
            owner_id=self.feed.owner_id,
            is_active=self.feed.is_active,
            language=self.feed.language,
            should_poll=True,
            http_etag="",
            http_last_modified="",
        )
        self.assertEqual(row.model_dump(), expected.model_dump())

    def test_list_feeds_includes_poll_validators(self) -> None:
        self.feed.http_etag = '"abc123"'
        self.feed.http_last_modified = "Wed, 12 Nov 2025 10:00:00 GMT"
        self.feed.save(update_fields=["http_etag", "http_last_modified", "updated_at"])
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        typed = FeedListResponse.model_validate(response.json())
        by_id = {row.id: row for row in typed.feeds}
        self.assertEqual(by_id[self.feed.id].http_etag, '"abc123"')
        self.assertEqual(
            by_id[self.feed.id].http_last_modified,
            "Wed, 12 Nov 2025 10:00:00 GMT",
        )

    def test_update_feed_poll_state(self) -> None:
        response = self.client.post(
            "/api/internal/feeds/poll-state/",
            data={
                "updates": [
                    {
                        "feed_id": self.feed.id,
                        "http_etag": '"v2"',
                        "http_last_modified": "Thu, 13 Nov 2025 11:00:00 GMT",
                    }
                ]
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.http_etag, '"v2"')
        self.assertEqual(self.feed.http_last_modified, "Thu, 13 Nov 2025 11:00:00 GMT")

        # Idempotent when unchanged.
        response = self.client.post(
            "/api/internal/feeds/poll-state/",
            data={
                "updates": [
                    {
                        "feed_id": self.feed.id,
                        "http_etag": '"v2"',
                        "http_last_modified": "Thu, 13 Nov 2025 11:00:00 GMT",
                    }
                ]
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 0)

    def test_update_feed_poll_state_unknown_feed(self) -> None:
        response = self.client.post(
            "/api/internal/feeds/poll-state/",
            data={"updates": [{"feed_id": 999999, "http_etag": '"x"'}]},
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_list_feeds_with_x_internal_token_header(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"X-Internal-Token": "test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        urls = {row["url"] for row in response.json()["feeds"]}
        self.assertIn(self.feed.url, urls)

    @override_settings(INTERNAL_API_TOKEN="")
    def test_list_feeds_unconfigured(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer anything"},
        )
        self.assertEqual(response.status_code, 503)


@override_settings(
    INTERNAL_API_TOKEN="test-internal-token",
    FEED_ITEMS_QUEUE_URL="https://sqs.example/queue",
)
class InternalFeedItemsApiTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="Feed Items Test",
            url="https://example.com/feed-items-test.xml",
            kind=Feed.SourceKind.CURATED,
        )
        self.item = FeedItem(
            feed_id=self.feed.id,
            id="guid-1",
            link="https://www.bbc.com/news/1",
            title="Hello",
            description="World",
            published_at="2026-11-04T10:00:00+00:00",
            thumbnail="",
        )

    @patch("news.api.enqueue_feed_items", return_value=1)
    def test_ingest_enqueues_new_items(self, mock_enqueue) -> None:
        response = self.client.post(
            "/api/internal/feed-items/",
            data=FeedItemIngestRequest(items=[self.item]).model_dump(),
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["accepted"], 1)
        self.assertEqual(payload["skipped_existing"], 0)
        self.assertEqual(payload["enqueued"], 1)
        mock_enqueue.assert_called_once()
        self.assertEqual(len(mock_enqueue.call_args.args[0]), 1)

    @patch("news.api.enqueue_feed_items", return_value=0)
    def test_ingest_skips_existing_articles(self, mock_enqueue) -> None:
        Article.objects.create(
            feed=self.feed,
            title="Hello",
            url=self.item.link,
            summary="World",
            published_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        )
        response = self.client.post(
            "/api/internal/feed-items/",
            data={"items": [self.item.model_dump()]},
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["accepted"], 0)
        self.assertEqual(payload["skipped_existing"], 1)
        self.assertEqual(payload["enqueued"], 0)
        mock_enqueue.assert_called_once_with([])


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class InternalArticlesApiTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="Articles Test",
            url="https://example.com/articles-test.xml",
            kind=Feed.SourceKind.CURATED,
        )

    def test_upsert_creates_article(self) -> None:
        embedding = [0.0] * 1024
        embedding[0] = 1.0
        response = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/1",
                "title": "Hello",
                "summary": "World",
                "published_at": "2026-11-04T10:00:00+00:00",
                "image_url": "https://cdn.example.com/thumb.jpg",
                "embedding": embedding,
                "embedding_model": "cohere.embed-multilingual-v3",
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["created"])
        self.assertIsNone(payload["story_thread_id"])
        article = Article.objects.get(pk=payload["article_id"])
        self.assertEqual(article.image_url, "https://cdn.example.com/thumb.jpg")
        self.assertEqual(article.embedding_model, "cohere.embed-multilingual-v3")
        self.assertIsNone(article.story_thread_id)

    def test_upsert_rejects_bad_embedding_size(self) -> None:
        response = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/bad-embed",
                "title": "Hello",
                "summary": "World",
                "published_at": "2026-11-04T10:00:00+00:00",
                "embedding": [0.1, 0.2],
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_upsert_is_idempotent(self) -> None:
        first = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/1",
                "title": "Hello",
                "summary": "World",
                "published_at": "2026-11-04T10:00:00+00:00",
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        second = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/1",
                "title": "Hello updated",
                "summary": "World",
                "published_at": "2026-11-04T10:00:00+00:00",
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["article_id"], second.json()["article_id"])
        self.assertEqual(Article.objects.count(), 1)
        self.assertEqual(Article.objects.get().title, "Hello updated")

    def test_upsert_persists_impact_tier(self) -> None:
        response = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/impact",
                "title": "Midterms: Blue Tsunami turns Texas Democrat",
                "summary": "Historic shift in Texas politics.",
                "published_at": "2026-11-04T10:00:00+00:00",
                "impact_tier": "major",
                "impact_rationale": "Major electoral shift with lasting impact.",
                "enrichment_status": "ok",
                "extract_model": "eu.amazon.nova-micro-v1:0",
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        article = Article.objects.get(url="https://www.bbc.com/news/impact")
        self.assertEqual(article.impact_tier, "major")
        self.assertEqual(article.impact_rationale, "Major electoral shift with lasting impact.")

    def test_upsert_sets_themes_and_records_suggestions(self) -> None:
        Theme.objects.update_or_create(
            slug="sports",
            defaults={"label": "Sports", "sort_order": 1, "is_active": True},
        )
        Theme.objects.update_or_create(
            slug="conflict",
            defaults={"label": "Conflict", "sort_order": 2, "is_active": True},
        )
        response = self.client.post(
            "/api/internal/articles/",
            data={
                "feed_id": self.feed.id,
                "url": "https://www.bbc.com/news/themes",
                "title": "Vinicius message from Sudan war",
                "summary": "Footballer reaches out.",
                "published_at": "2026-11-04T10:00:00+00:00",
                "theme_slugs": ["sports", "conflict"],
                "suggested_themes": ["war-crimes", "sports"],
            },
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        article = Article.objects.get(url="https://www.bbc.com/news/themes")
        self.assertEqual(
            set(article.themes.values_list("slug", flat=True)),
            {"sports", "conflict"},
        )
        suggestion = ThemeSuggestion.objects.get(raw="war-crimes")
        self.assertEqual(suggestion.count, 1)
        self.assertFalse(ThemeSuggestion.objects.filter(raw="sports").exists())
