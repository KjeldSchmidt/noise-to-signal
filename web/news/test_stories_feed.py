import re
from datetime import UTC, datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from news.models import Article, Feed, ImpactTier, StoryThread
from news.services.stories_feed import (
    HALF_LIFE_HOURS,
    build_stories_feed,
    build_stories_feed_page,
    format_thread_span,
    thread_timeline_articles,
)


class StoriesFeedServiceTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="BBC World",
            url="https://example.com/stories-feed-test.xml",
            site_url="https://www.bbc.com/news",
            kind=Feed.SourceKind.CURATED,
        )
        self.other_feed = Feed.objects.create(
            title="NPR News",
            url="https://example.com/stories-feed-other.xml",
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

        entries = build_stories_feed(
            [self.feed.id, self.other_feed.id],
            now=self.now + timedelta(hours=3),
        )

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
        self.assertEqual(entries[0].image_url, "https://example.com/quake.jpg")
        self.assertEqual(entries[1].kind, "article")
        assert entries[1].article is not None
        self.assertEqual(entries[1].article.id, plain.id)

    def test_thread_preview_uses_older_member_image_when_lead_has_none(self) -> None:
        thread = StoryThread.objects.create(
            label="Image Fallback",
            last_published_at=self.now + timedelta(hours=2),
        )
        Article.objects.create(
            feed=self.feed,
            title="Older with image",
            url="https://example.com/img-old",
            published_at=self.now,
            story_thread=thread,
            image_url="https://example.com/good.jpg",
        )
        Article.objects.create(
            feed=self.other_feed,
            title="Newer without image",
            url="https://example.com/img-new",
            published_at=self.now + timedelta(hours=2),
            story_thread=thread,
        )

        entries = build_stories_feed(
            [self.feed.id, self.other_feed.id],
            now=self.now + timedelta(hours=3),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].kind, "thread")
        assert entries[0].lead_article is not None
        self.assertEqual(entries[0].lead_article.title, "Newer without image")
        self.assertEqual(entries[0].image_url, "https://example.com/good.jpg")

    def test_fresh_major_outranks_fresh_ephemeral(self) -> None:
        Article.objects.create(
            feed=self.feed,
            title="Major event",
            url="https://example.com/major",
            published_at=self.now,
            impact_tier=ImpactTier.MAJOR,
        )
        Article.objects.create(
            feed=self.feed,
            title="Ephemeral blip",
            url="https://example.com/ephemeral",
            published_at=self.now,
            impact_tier=ImpactTier.EPHEMERAL,
        )

        entries = build_stories_feed([self.feed.id], now=self.now)
        self.assertEqual(
            [e.article.title for e in entries if e.article],
            [
                "Major event",
                "Ephemeral blip",
            ],
        )

    def test_decayed_major_beats_fresh_ephemeral(self) -> None:
        Article.objects.create(
            feed=self.feed,
            title="Yesterday major",
            url="https://example.com/old-major",
            published_at=self.now - timedelta(hours=HALF_LIFE_HOURS),
            impact_tier=ImpactTier.MAJOR,
        )
        Article.objects.create(
            feed=self.feed,
            title="Fresh fluff",
            url="https://example.com/fresh-ephemeral",
            published_at=self.now,
            impact_tier=ImpactTier.EPHEMERAL,
        )

        entries = build_stories_feed([self.feed.id], now=self.now)
        assert entries[0].article is not None
        assert entries[1].article is not None
        self.assertEqual(entries[0].article.title, "Yesterday major")
        self.assertEqual(entries[1].article.title, "Fresh fluff")

    def test_two_ephemeral_thread_loses_to_standalone_major(self) -> None:
        thread = StoryThread.objects.create(
            label="Minor Blips",
            last_published_at=self.now,
        )
        Article.objects.create(
            feed=self.feed,
            title="Blip one",
            url="https://example.com/blip-1",
            published_at=self.now - timedelta(hours=1),
            story_thread=thread,
            impact_tier=ImpactTier.EPHEMERAL,
        )
        Article.objects.create(
            feed=self.other_feed,
            title="Blip two",
            url="https://example.com/blip-2",
            published_at=self.now,
            story_thread=thread,
            impact_tier=ImpactTier.EPHEMERAL,
        )
        Article.objects.create(
            feed=self.feed,
            title="Lone major",
            url="https://example.com/lone-major",
            published_at=self.now,
            impact_tier=ImpactTier.MAJOR,
        )

        entries = build_stories_feed(
            [self.feed.id, self.other_feed.id],
            now=self.now,
        )
        self.assertEqual(entries[0].kind, "article")
        assert entries[0].article is not None
        self.assertEqual(entries[0].article.title, "Lone major")
        self.assertEqual(entries[1].kind, "thread")

    def test_thread_coverage_boosts_above_lone_notable(self) -> None:
        thread = StoryThread.objects.create(
            label="Covered Story",
            last_published_at=self.now,
        )
        Article.objects.create(
            feed=self.feed,
            title="Notable with coverage",
            url="https://example.com/covered-1",
            published_at=self.now,
            story_thread=thread,
            impact_tier=ImpactTier.NOTABLE,
        )
        Article.objects.create(
            feed=self.other_feed,
            title="Extra coverage",
            url="https://example.com/covered-2",
            published_at=self.now,
            story_thread=thread,
            impact_tier=ImpactTier.EPHEMERAL,
        )
        Article.objects.create(
            feed=self.feed,
            title="Lone notable",
            url="https://example.com/lone-notable",
            published_at=self.now,
            impact_tier=ImpactTier.NOTABLE,
        )

        entries = build_stories_feed(
            [self.feed.id, self.other_feed.id],
            now=self.now,
        )
        self.assertEqual(entries[0].kind, "thread")
        self.assertEqual(entries[1].kind, "article")
        assert entries[1].article is not None
        self.assertEqual(entries[1].article.title, "Lone notable")

    def test_since_partition_and_pagination(self) -> None:
        for i in range(5):
            Article.objects.create(
                feed=self.feed,
                title=f"New {i}",
                url=f"https://example.com/new-{i}",
                published_at=self.now + timedelta(hours=i + 1),
                impact_tier=ImpactTier.EPHEMERAL,
            )
        for i in range(5):
            Article.objects.create(
                feed=self.feed,
                title=f"Old {i}",
                url=f"https://example.com/old-{i}",
                published_at=self.now - timedelta(hours=i + 1),
                impact_tier=ImpactTier.EPHEMERAL,
            )

        since = self.now
        page1 = build_stories_feed_page(
            [self.feed.id],
            page=1,
            page_size=4,
            since=since,
            now=self.now + timedelta(hours=10),
        )
        self.assertEqual(len(page1.entries), 4)
        self.assertTrue(all(e.is_new for e in page1.entries))
        self.assertTrue(page1.has_next)
        self.assertFalse(page1.has_previous)

        page2 = build_stories_feed_page(
            [self.feed.id],
            page=2,
            page_size=4,
            since=since,
            now=self.now + timedelta(hours=10),
        )
        self.assertEqual(len(page2.entries), 4)
        self.assertTrue(page2.has_previous)
        self.assertTrue(page2.has_next)
        # Concat order: all 5 new, then earlier — page 2 starts with last new.
        self.assertTrue(page2.entries[0].is_new)
        self.assertFalse(page2.entries[1].is_new)

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
            url="https://example.com/stories-feed-test-2.xml",
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
        self.assertContains(response, "stories-visit.js")

    def test_stories_page_pagination_and_since(self) -> None:
        for i in range(25):
            Article.objects.create(
                feed=self.feed,
                title=f"Extra story {i}",
                url=f"https://example.com/extra-{i}",
                published_at=self.now - timedelta(hours=i),
                impact_tier=ImpactTier.EPHEMERAL,
            )
        page2 = self.client.get(reverse("stories"), {"page": "2"})
        self.assertEqual(page2.status_code, 200)
        self.assertContains(page2, "stories-pager")
        self.assertContains(page2, ">First</a>")
        self.assertContains(page2, ">Previous</a>")
        self.assertContains(page2, "Page 2")
        self.assertNotContains(page2, " of ")

        since = (self.now - timedelta(hours=2)).isoformat()
        with_since = self.client.get(reverse("stories"), {"since": since, "page": "1"})
        self.assertEqual(with_since.status_code, 200)
        self.assertContains(with_since, "New since your last visit")
        self.assertContains(with_since, "since=")

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

    def test_thread_detail_opens_recent_summaries_only(self) -> None:
        now = timezone.now()
        thread = StoryThread.objects.create(
            label="Cutoff Thread",
            last_published_at=now,
        )
        Article.objects.create(
            feed=self.feed,
            title="Fresh update",
            url="https://example.com/fresh",
            summary="Published within a day",
            published_at=now - timedelta(hours=6),
            story_thread=thread,
        )
        Article.objects.create(
            feed=self.feed,
            title="Older update",
            url="https://example.com/older",
            summary="Published two days ago",
            published_at=now - timedelta(hours=36),
            story_thread=thread,
        )
        response = self.client.get(reverse("story_thread", args=[thread.id]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        blocks = re.findall(
            r'<div\s+class="timeline-summary( is-expanded)?"[^>]*>(.*?)</div>',
            body,
            flags=re.DOTALL,
        )
        self.assertEqual(len(blocks), 2)
        by_text = {
            ("fresh" if "within a day" in chunk else "older"): bool(is_expanded)
            for is_expanded, chunk in blocks
        }
        self.assertTrue(by_text["fresh"])
        self.assertFalse(by_text["older"])
        self.assertNotIn(">Summary<", body)
