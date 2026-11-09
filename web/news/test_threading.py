from datetime import datetime, timedelta, timezone

from django.test import TestCase

from news.models import Article, Feed, StoryThread
from news.services.threading import (
    DEDUP_SIMILARITY,
    THREAD_SIMILARITY,
    assign_story_thread,
    cosine_similarity,
)


def _vec(seed: float) -> list[float]:
    values = [0.0] * 1024
    values[0] = seed
    values[1] = (1.0 - seed * seed) ** 0.5 if abs(seed) < 1 else 0.0
    return values


class ThreadingTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC World",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            kind=Feed.SourceKind.CURATED,
        )
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def test_cosine_similarity_identical(self) -> None:
        v = _vec(1.0)
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0, places=5)

    def test_new_article_creates_thread(self) -> None:
        article = Article.objects.create(
            feed=self.feed,
            title="Event starts",
            url="https://example.com/a",
            summary="First coverage",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(article)
        article.refresh_from_db()
        self.assertIsNotNone(article.story_thread_id)
        self.assertIsNone(article.near_duplicate_of_id)
        self.assertEqual(StoryThread.objects.count(), 1)

    def test_near_duplicate_joins_same_thread(self) -> None:
        first = Article.objects.create(
            feed=self.feed,
            title="Quake hits city",
            url="https://example.com/a",
            summary="Strong earthquake reported",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(first)

        second = Article.objects.create(
            feed=self.feed,
            title="Quake hits city — update",
            url="https://example.com/b",
            summary="Strong earthquake reported downtown",
            published_at=self.now + timedelta(hours=1),
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(second)
        second.refresh_from_db()
        first.refresh_from_db()

        self.assertGreaterEqual(DEDUP_SIMILARITY, 0.9)
        self.assertEqual(second.near_duplicate_of_id, first.id)
        self.assertEqual(second.story_thread_id, first.story_thread_id)
        self.assertEqual(StoryThread.objects.count(), 1)

    def test_soft_match_extends_open_thread(self) -> None:
        # cos((1,0), (0.85, sqrt(1-0.85^2))) ≈ 0.85 — between thread and dedup thresholds.
        base = _vec(1.0)
        follow = _vec(0.85)

        self.assertGreaterEqual(cosine_similarity(base, follow), THREAD_SIMILARITY)
        self.assertLess(cosine_similarity(base, follow), DEDUP_SIMILARITY)

        first = Article.objects.create(
            feed=self.feed,
            title="Talks begin",
            url="https://example.com/a",
            summary="Negotiators meet",
            published_at=self.now - timedelta(days=7),
            embedding=base,
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(first)

        later = Article.objects.create(
            feed=self.feed,
            title="Talks stall",
            url="https://example.com/b",
            summary="Negotiators adjourn without deal",
            published_at=self.now,
            embedding=follow,
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(later)
        later.refresh_from_db()
        first.refresh_from_db()

        self.assertIsNone(later.near_duplicate_of_id)
        self.assertEqual(later.story_thread_id, first.story_thread_id)
        self.assertEqual(StoryThread.objects.count(), 1)
