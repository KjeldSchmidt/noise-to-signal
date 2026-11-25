"""Tests for personalized brief freshness, API, and page kickoff."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from n2s_api import BriefCompleteRequest, BriefItemUpsert

from news.models import (
    Article,
    Feed,
    ImpactTier,
    RelevanceFeedback,
    StoryThread,
    UserBrief,
    UserBriefItem,
)
from news.services.brief import BRIEF_TTL, brief_is_fresh, resolve_brief_page
from news.services.brief_context import build_brief_user_context
from news.services.thread_summary import (
    THREAD_SUMMARY_TTL,
    maybe_invoke_thread_summary,
    should_refresh_thread_summary,
)

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    # django-stubs types User.objects as Manager[AbstractBaseUser] without create_user.
    return cast(Any, User.objects).create_user(**kwargs)


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class BriefApiTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="brief-api", password="x")
        self.feed = Feed.objects.create(
            title="Brief Feed",
            url="https://example.com/brief.xml",
            site_url="https://example.com/",
            category="World",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.article = Article.objects.create(
            feed=self.feed,
            title="Brief Article",
            url="https://example.com/a1",
            summary="Summary",
            published_at=timezone.now(),
            impact_tier=ImpactTier.MAJOR,
        )
        self.brief = UserBrief.objects.create(user=self.user, status=UserBrief.Status.PENDING)

    def test_complete_brief_ready(self) -> None:
        payload = BriefCompleteRequest(
            brief_id=self.brief.id,
            user_id=self.user.id,
            status="ready",
            items=[
                BriefItemUpsert(
                    kind="article",
                    article_id=self.article.id,
                    rank=1,
                    score=0.9,
                    reason="Fits your interests.",
                )
            ],
        )
        response = self.client.post(
            "/api/internal/briefs/complete/",
            data=payload.model_dump_json(),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(response.status_code, 200)
        self.brief.refresh_from_db()
        self.assertEqual(self.brief.status, UserBrief.Status.READY)
        self.assertEqual(UserBriefItem.objects.filter(brief=self.brief).count(), 1)

    def test_complete_brief_with_thread(self) -> None:
        thread = StoryThread.objects.create(
            label="Quake Coverage",
            last_published_at=timezone.now(),
            summary="A major quake struck overnight.",
            summarized_at=timezone.now(),
        )
        payload = BriefCompleteRequest(
            brief_id=self.brief.id,
            user_id=self.user.id,
            status="ready",
            items=[
                BriefItemUpsert(
                    kind="thread",
                    story_thread_id=thread.id,
                    rank=1,
                    score=0.88,
                    reason="Developing story in your region.",
                )
            ],
        )
        response = self.client.post(
            "/api/internal/briefs/complete/",
            data=payload.model_dump_json(),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(response.status_code, 200)
        item = UserBriefItem.objects.get(brief=self.brief)
        self.assertEqual(item.story_thread_id, thread.id)
        self.assertIsNone(item.article_id)

    def test_brief_user_context(self) -> None:
        response = self.client.get(
            f"/api/internal/briefs/users/{self.user.id}/context/",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], self.user.id)
        self.assertIn("candidates", body)

    def test_story_thread_summary_roundtrip(self) -> None:
        thread = StoryThread.objects.create(
            label="Talks",
            last_published_at=timezone.now(),
        )
        Article.objects.create(
            feed=self.feed,
            title="Talks resume",
            url="https://example.com/talks",
            summary="Negotiators returned to the table.",
            published_at=timezone.now(),
            story_thread=thread,
        )
        ctx = self.client.get(
            f"/api/internal/story-threads/{thread.id}/summary-context/",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(ctx.status_code, 200)
        self.assertEqual(ctx.json()["story_thread_id"], thread.id)
        self.assertEqual(len(ctx.json()["articles"]), 1)

        update = self.client.post(
            "/api/internal/story-threads/summary/",
            data=(
                f'{{"story_thread_id": {thread.id}, '
                f'"summary": "Negotiators resumed talks overnight."}}'
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(update.status_code, 200)
        thread.refresh_from_db()
        self.assertIn("Negotiators", thread.summary)
        self.assertIsNotNone(thread.summarized_at)


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class BriefThreadCandidateTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="brief-thread", password="x")
        self.feed = Feed.objects.create(
            title="Thread Feed",
            url="https://example.com/thread.xml",
            site_url="https://example.com/",
            category="World",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.thread = StoryThread.objects.create(
            label="City Quake",
            last_published_at=timezone.now(),
            summary="AI digest of the quake coverage.",
            summarized_at=timezone.now(),
        )
        now = timezone.now()
        self.lead = Article.objects.create(
            feed=self.feed,
            title="Quake hits city",
            url="https://example.com/q1",
            summary="Lead RSS",
            published_at=now,
            story_thread=self.thread,
            impact_tier=ImpactTier.MAJOR,
        )
        self.member = Article.objects.create(
            feed=self.feed,
            title="Aftershocks continue",
            url="https://example.com/q2",
            summary="Member RSS",
            published_at=now - timedelta(hours=1),
            story_thread=self.thread,
            impact_tier=ImpactTier.NOTABLE,
        )

    def test_context_emits_thread_candidate(self) -> None:
        with patch(
            "news.services.brief_context.enabled_feed_ids",
            return_value=[self.feed.id],
        ):
            ctx = build_brief_user_context(self.user.id)
        kinds = {c.kind for c in ctx.candidates}
        self.assertIn("thread", kinds)
        thread_cand = next(c for c in ctx.candidates if c.kind == "thread")
        self.assertEqual(thread_cand.story_thread_id, self.thread.id)
        self.assertEqual(thread_cand.summary, "AI digest of the quake coverage.")
        self.assertGreaterEqual(thread_cand.article_count, 2)

    def test_context_excludes_thread_when_any_member_judged(self) -> None:
        RelevanceFeedback.objects.create(
            user=self.user,
            article=self.member,
            verdict=RelevanceFeedback.Verdict.NOT_RELEVANT,
        )
        with patch(
            "news.services.brief_context.enabled_feed_ids",
            return_value=[self.feed.id],
        ):
            ctx = build_brief_user_context(self.user.id)
        self.assertFalse(any(c.kind == "thread" for c in ctx.candidates))
        self.assertFalse(any(c.article_id == self.lead.id for c in ctx.candidates))


class ThreadSummaryFreshnessTests(TestCase):
    def setUp(self) -> None:
        self.thread = StoryThread.objects.create(
            label="Freshness",
            last_published_at=timezone.now(),
        )

    def test_should_refresh_when_missing(self) -> None:
        self.assertTrue(should_refresh_thread_summary(self.thread))

    def test_fresh_summary_skips_refresh(self) -> None:
        self.thread.summary = "Still fresh."
        self.thread.summarized_at = timezone.now()
        self.thread.save(update_fields=["summary", "summarized_at", "updated_at"])
        self.assertFalse(should_refresh_thread_summary(self.thread))

    def test_stale_summary_refreshes(self) -> None:
        self.thread.summary = "Old digest."
        self.thread.summarized_at = timezone.now() - THREAD_SUMMARY_TTL - timedelta(minutes=1)
        self.thread.save(update_fields=["summary", "summarized_at", "updated_at"])
        self.assertTrue(should_refresh_thread_summary(self.thread))

    @override_settings(DEBUG=True, STORY_SUMMARIZER_FUNCTION_NAME="")
    def test_maybe_invoke_writes_stub(self) -> None:
        invoked = maybe_invoke_thread_summary(self.thread.id)
        self.assertTrue(invoked)
        self.thread.refresh_from_db()
        self.assertTrue(self.thread.summary)
        self.assertIsNotNone(self.thread.summarized_at)

    @override_settings(DEBUG=True, STORY_SUMMARIZER_FUNCTION_NAME="")
    def test_maybe_invoke_skips_when_fresh(self) -> None:
        self.thread.summary = "Fresh."
        self.thread.summarized_at = timezone.now()
        self.thread.save(update_fields=["summary", "summarized_at", "updated_at"])
        self.assertFalse(maybe_invoke_thread_summary(self.thread.id))


class BriefFreshnessTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="brief-fresh", password="x")
        self.feed = Feed.objects.create(
            title="Fresh Feed",
            url="https://example.com/fresh.xml",
            site_url="https://example.com/",
            category="World",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )

    def test_fresh_ready_is_caught_up_without_kick(self) -> None:
        brief = UserBrief.objects.create(
            user=self.user,
            status=UserBrief.Status.READY,
            ready_at=timezone.now(),
        )
        self.assertTrue(brief_is_fresh(brief))
        with patch("news.services.brief.enabled_feed_ids", return_value=[self.feed.id]):
            state = resolve_brief_page(self.user)
        self.assertEqual(state.phase, "caught_up")
        self.assertFalse(state.kick)
        assert state.brief is not None
        self.assertEqual(state.brief.id, brief.id)

    def test_stale_ready_starts_new_pending(self) -> None:
        UserBrief.objects.create(
            user=self.user,
            status=UserBrief.Status.READY,
            ready_at=timezone.now() - BRIEF_TTL - timedelta(minutes=1),
        )
        with patch("news.services.brief.enabled_feed_ids", return_value=[self.feed.id]):
            state = resolve_brief_page(self.user)
        self.assertEqual(state.phase, "personalizing")
        self.assertTrue(state.kick)
        assert state.brief is not None
        self.assertEqual(state.brief.status, UserBrief.Status.PENDING)


@override_settings(DEBUG=True, BRIEF_BUILDER_FUNCTION_NAME="")
class BriefPageTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="brief-page", password="x")
        self.client = Client()
        self.client.force_login(self.user)
        self.feed = Feed.objects.create(
            title="Page Feed",
            url="https://example.com/page.xml",
            site_url="https://example.com/",
            category="World",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        Article.objects.create(
            feed=self.feed,
            title="Page Article",
            url="https://example.com/page-a",
            summary="Hi",
            published_at=timezone.now(),
        )

    @patch("news.views.enabled_feed_ids", return_value=[1])
    @patch("news.views.invoke_brief_builder")
    def test_brief_page_kicks_builder(self, mock_invoke: Any, mock_feeds: Any) -> None:
        mock_feeds.return_value = [self.feed.id]
        with patch("news.services.brief.enabled_feed_ids", return_value=[self.feed.id]):
            response = self.client.get(reverse("brief"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personalizing")
        mock_invoke.assert_called_once()
        brief = UserBrief.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(brief.status, UserBrief.Status.PENDING)

    def test_brief_status_endpoint(self) -> None:
        brief = UserBrief.objects.create(user=self.user, status=UserBrief.Status.PENDING)
        response = self.client.get(reverse("brief_status", kwargs={"brief_id": brief.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
