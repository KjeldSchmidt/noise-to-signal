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

from news.models import Article, Feed, UserBrief, UserBriefItem
from news.services.brief import BRIEF_TTL, brief_is_fresh, resolve_brief_page

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
        )
        self.brief = UserBrief.objects.create(user=self.user, status=UserBrief.Status.PENDING)

    def test_complete_brief_ready(self) -> None:
        payload = BriefCompleteRequest(
            brief_id=self.brief.id,
            user_id=self.user.id,
            status="ready",
            items=[
                BriefItemUpsert(
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

    def test_brief_user_context(self) -> None:
        response = self.client.get(
            f"/api/internal/briefs/users/{self.user.id}/context/",
            HTTP_AUTHORIZATION="Bearer test-internal-token",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], self.user.id)
        self.assertIn("candidates", body)


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
    def test_brief_page_kicks_builder(self, mock_invoke, mock_feeds) -> None:
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
