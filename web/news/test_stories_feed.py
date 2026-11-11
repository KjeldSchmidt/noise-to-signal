from datetime import UTC, datetime, timedelta

from django.test import TestCase
from django.urls import reverse

from news.models import Article, Feed, StoryThread
from news.services.stories_feed import (
    build_stories_feed,
    format_thread_span,
    thread_timeline_articles,
)


class StoriesFeedServiceTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC World",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            site_url="https://www.bbc.com/news",
            kind=Feed.SourceKind.CURATED,
        )
        self.other_feed = Feed.objects.create(
            title="NPR News",
            url="https://feeds.npr.org/1001/rss.xml",
            site_url="https://www.npr.org",
            kind=Feed.SourceKind.CURATED,
        )
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def test_mixed_feed_collapses_thread_and_keeps_plain_article(self) -> None:
        thread = StoryThread.objects.create(
            label="City Earthquake",
            last_published_at=self.now + timedelta(hours=2),
        )
        Article.objects.create(
            feed=self.feed,
            title="Quake hits city",
            url="https://example.com/a",
            summary="First report",
            published_at=self.now,
            story_thread=thread,
        )
        Article.objects.create(
            feed=self.other_feed,
            title="Quake update",
            url="https://example.com/b",
            summary="Later report",
            published_at=self.now + timedelta(hours=2),
            story_thread=thread,
            image_url="https://example.com/quake.jpg",
        )
        plain = Article.objects.create(
            feed=self.feed,
            title="Unrelated sports score",
            url="https://example.com/c",
            summary="Game ended",
            published_at=self.now + timedelta(hours=1),
        )
        Article.objects.create(
            feed=self.feed,
            title="Near-dup of quake",
            url="https://example.com/d",
            summary="Copy",
            published_at=self.now + timedelta(hours=3),
            near_duplicate_of=plain,
        )

        entries = build_stories_feed([self.feed.id, self.other_feed.id])

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].kind, "thread")
        assert entries[0].thread is not None
        self.assertEqual(entries[0].thread.id, thread.id)
        self.assertEqual(entries[0].article_count, 2)
        assert entries[0].lead_article is not None
        self.assertEqual(entries[0].lead_article.title, "Quake update")
        self.assertEqual(
            [f.id for f in entries[0].source_feeds],
            [self.other_feed.id, self.feed.id],
        )
        self.assertEqual(entries[0].span_label, "2 hours")
        self.assertEqual(entries[1].kind, "article")
        assert entries[1].article is not None
        self.assertEqual(entries[1].article.id, plain.id)

    def test_format_thread_span(self) -> None:
        start = self.now
        self.assertEqual(format_thread_span(start, start + timedelta(minutes=10)), "same day")
        self.assertEqual(format_thread_span(start, start + timedelta(hours=5)), "5 hours")
        self.assertEqual(format_thread_span(start, start + timedelta(days=3)), "3 days")

    def test_timeline_articles_newest_first(self) -> None:
        thread = StoryThread.objects.create(
            label="Talks",
            last_published_at=self.now + timedelta(hours=5),
        )
        later = Article.objects.create(
            feed=self.feed,
            title="Talks continue",
            url="https://example.com/later",
            published_at=self.now + timedelta(hours=5),
            story_thread=thread,
        )
        earlier = Article.objects.create(
            feed=self.feed,
            title="Talks begin",
            url="https://example.com/earlier",
            published_at=self.now,
            story_thread=thread,
        )

        ordered = thread_timeline_articles(thread)
        self.assertEqual([a.id for a in ordered], [later.id, earlier.id])


class StoryThreadViewTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC World",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            kind=Feed.SourceKind.CURATED,
        )
        self.out_of_scope = Feed.objects.create(
            title="Custom only",
            url="https://example.com/custom.xml",
            kind=Feed.SourceKind.CUSTOM,
        )
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
        self.thread = StoryThread.objects.create(
            label="Peace Talks",
            last_published_at=self.now + timedelta(hours=2),
        )
        Article.objects.create(
            feed=self.feed,
            title="Talks open",
            url="https://example.com/open",
            summary="Delegates arrive",
            published_at=self.now,
            story_thread=self.thread,
        )
        Article.objects.create(
            feed=self.feed,
            title="Talks advance",
            url="https://example.com/advance",
            summary="Draft agreement",
            published_at=self.now + timedelta(hours=2),
            story_thread=self.thread,
        )

    def test_stories_page_shows_thread_card(self) -> None:
        response = self.client.get(reverse("stories"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peace Talks")
        self.assertContains(response, "2 articles")
        self.assertContains(response, "story-stack")
        self.assertContains(response, reverse("story_thread", args=[self.thread.id]))

    def test_thread_detail_ok_when_in_scope(self) -> None:
        response = self.client.get(reverse("story_thread", args=[self.thread.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peace Talks")
        self.assertContains(response, "Talks open")
        self.assertContains(response, "Talks advance")
        # Newest first in markup order.
        body = response.content.decode()
        self.assertLess(body.index("Talks advance"), body.index("Talks open"))

    def test_thread_detail_404_when_out_of_scope(self) -> None:
        hidden = StoryThread.objects.create(
            label="Hidden Thread",
            last_published_at=self.now,
        )
        Article.objects.create(
            feed=self.out_of_scope,
            title="Secret item",
            url="https://example.com/secret",
            published_at=self.now,
            story_thread=hidden,
        )
        response = self.client.get(reverse("story_thread", args=[hidden.id]))
        self.assertEqual(response.status_code, 404)
