from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from news.models import Article, Feed
from news.services.requeue import articles_for_requeue


class RequeueSelectTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC",
            url="https://example.com/rss",
            kind=Feed.SourceKind.CURATED,
        )
        now = timezone.now()
        self.fresh = Article.objects.create(
            feed=self.feed,
            title="Fresh enrich",
            url="https://example.com/a",
            summary="",
            published_at=now - timedelta(hours=6),
            enriched_at=now - timedelta(minutes=30),
        )
        self.stale = Article.objects.create(
            feed=self.feed,
            title="Stale enrich",
            url="https://example.com/b",
            summary="",
            published_at=now - timedelta(hours=48),
            enriched_at=now - timedelta(hours=24),
        )
        self.never = Article.objects.create(
            feed=self.feed,
            title="Never",
            url="https://example.com/c",
            summary="",
            published_at=now - timedelta(hours=10),
            enriched_at=None,
        )

    def test_enriched_before_hours_skips_recent(self) -> None:
        qs = articles_for_requeue(since_hours=72, enriched_before_hours=1)
        ids = set(qs.values_list("id", flat=True))
        self.assertNotIn(self.fresh.id, ids)
        self.assertIn(self.stale.id, ids)
        self.assertIn(self.never.id, ids)
