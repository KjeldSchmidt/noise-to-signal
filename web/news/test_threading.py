from datetime import UTC, datetime, timedelta

from django.test import TestCase

from news.models import Article, Feed, StoryThread
from news.services.threading import (
    DEDUP_SIMILARITY,
    THREAD_SIMILARITY,
    assign_story_thread,
    cosine_similarity,
    dissolve_singleton_threads,
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
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def test_cosine_similarity_identical(self) -> None:
        v = _vec(1.0)
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0, places=5)

    def test_lonely_article_stays_unthreaded(self) -> None:
        article = Article.objects.create(
            feed=self.feed,
            title="Event starts",
            url="https://example.com/a",
            summary="First coverage",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
            story_label="Event Starts",
        )
        assign_story_thread(article)
        article.refresh_from_db()
        self.assertIsNone(article.story_thread_id)
        self.assertIsNone(article.near_duplicate_of_id)
        self.assertEqual(StoryThread.objects.count(), 0)

    def test_near_duplicate_creates_shared_thread(self) -> None:
        first = Article.objects.create(
            feed=self.feed,
            title="Quake hits city",
            url="https://example.com/a",
            summary="Strong earthquake reported",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
            story_label="City Earthquake",
        )
        assign_story_thread(first)
        first.refresh_from_db()
        self.assertIsNone(first.story_thread_id)

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
        self.assertIsNotNone(second.story_thread_id)
        self.assertEqual(second.story_thread_id, first.story_thread_id)
        self.assertEqual(StoryThread.objects.count(), 1)
        self.assertEqual(second.story_thread.label, "City Earthquake")

    def test_soft_peer_pair_creates_thread(self) -> None:
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
            story_label="Peace Talks",
        )
        assign_story_thread(first)
        first.refresh_from_db()
        self.assertIsNone(first.story_thread_id)

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
        self.assertIsNotNone(later.story_thread_id)
        self.assertEqual(later.story_thread_id, first.story_thread_id)
        self.assertEqual(StoryThread.objects.count(), 1)
        self.assertEqual(later.story_thread.label, "Peace Talks")

    def test_soft_match_extends_open_thread(self) -> None:
        base = _vec(1.0)
        follow = _vec(0.85)
        third = _vec(0.82)

        first = Article.objects.create(
            feed=self.feed,
            title="Talks begin",
            url="https://example.com/a",
            summary="Negotiators meet",
            published_at=self.now - timedelta(days=7),
            embedding=base,
            embedding_model="test",
            embedded_at=self.now,
            story_label="Peace Talks",
        )
        second = Article.objects.create(
            feed=self.feed,
            title="Talks stall",
            url="https://example.com/b",
            summary="Negotiators adjourn",
            published_at=self.now - timedelta(days=3),
            embedding=follow,
            embedding_model="test",
            embedded_at=self.now,
        )
        assign_story_thread(first)
        assign_story_thread(second)
        second.refresh_from_db()
        thread_id = second.story_thread_id
        self.assertIsNotNone(thread_id)

        later = Article.objects.create(
            feed=self.feed,
            title="Talks resume",
            url="https://example.com/c",
            summary="Sides return to table",
            published_at=self.now,
            embedding=third,
            embedding_model="test",
            embedded_at=self.now,
            story_label="Should Not Replace",
        )
        assign_story_thread(later)
        later.refresh_from_db()
        thread = StoryThread.objects.get(pk=thread_id)
        self.assertEqual(later.story_thread_id, thread_id)
        self.assertEqual(thread.label, "Peace Talks")

    def test_already_threaded_is_noop(self) -> None:
        thread = StoryThread.objects.create(
            label="Existing",
            centroid=_vec(1.0),
            last_published_at=self.now,
        )
        article = Article.objects.create(
            feed=self.feed,
            title="Locked in",
            url="https://example.com/a",
            summary="Already clustered",
            published_at=self.now,
            embedding=_vec(0.5),
            embedding_model="test",
            embedded_at=self.now,
            story_thread=thread,
        )
        assign_story_thread(article)
        article.refresh_from_db()
        self.assertEqual(article.story_thread_id, thread.id)
        self.assertEqual(StoryThread.objects.count(), 1)

    def test_dissolve_singleton_threads(self) -> None:
        thread = StoryThread.objects.create(
            label="Lonely",
            centroid=_vec(1.0),
            last_published_at=self.now,
        )
        article = Article.objects.create(
            feed=self.feed,
            title="Alone",
            url="https://example.com/a",
            summary="Only member",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
            story_thread=thread,
        )
        cleared, deleted = dissolve_singleton_threads()
        article.refresh_from_db()
        self.assertEqual(cleared, 1)
        self.assertGreaterEqual(deleted, 1)
        self.assertIsNone(article.story_thread_id)
        self.assertEqual(StoryThread.objects.count(), 0)
