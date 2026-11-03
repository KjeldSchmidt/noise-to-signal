from dataclasses import asdict

from django.test import TestCase, override_settings
from n2s_api import Feed as FeedDTO, FeedListResponse

from news.models import Feed


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class InternalFeedsApiTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC World",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            site_url="https://www.bbc.com/news/world",
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
        typed = FeedListResponse(
            feeds=[FeedDTO(**item) for item in response.json()["feeds"]]
        )
        self.assertEqual(len(typed.feeds), 1)
        self.assertEqual(typed.feeds[0].id, self.feed.id)
        self.assertEqual(typed.feeds[0].url, self.feed.url)
        self.assertTrue(typed.feeds[0].is_active)
        self.assertEqual(
            response.json(),
            asdict(
                FeedListResponse(
                    feeds=[
                        FeedDTO(
                            id=self.feed.id,
                            title=self.feed.title,
                            url=self.feed.url,
                            site_url=self.feed.site_url,
                            description=self.feed.description,
                            category=self.feed.category,
                            kind=self.feed.kind,
                            owner_id=self.feed.owner_id,
                            is_active=self.feed.is_active,
                        )
                    ]
                )
            ),
        )

    def test_list_feeds_with_x_internal_token_header(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"X-Internal-Token": "test-internal-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["feeds"]), 1)

    @override_settings(INTERNAL_API_TOKEN="")
    def test_list_feeds_unconfigured(self) -> None:
        response = self.client.get(
            "/api/internal/feeds/",
            headers={"Authorization": "Bearer anything"},
        )
        self.assertEqual(response.status_code, 503)
