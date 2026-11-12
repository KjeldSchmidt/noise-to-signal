"""Tests for news chat rate limits, AuthZ, and endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from n2s_api import ChatWorkerResponse

from news.models import Article, Feed, StoryThread
from news.services import chat_rate_limit
from news.services.chat_rate_limit import DAY_LIMIT, MINUTE_LIMIT, check_and_increment

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    # django-stubs types User.objects as Manager[AbstractBaseUser] without create_user.
    return cast(Any, User.objects).create_user(**kwargs)


class ChatRateLimitTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="chat-rl", password="x")

    def test_allows_under_limits(self) -> None:
        decision = check_and_increment(self.user)
        self.assertTrue(decision.allowed)

    def test_minute_limit_returns_429_decision(self) -> None:
        for _ in range(MINUTE_LIMIT):
            self.assertTrue(check_and_increment(self.user).allowed)
        blocked = check_and_increment(self.user)
        self.assertFalse(blocked.allowed)
        self.assertIn("minute", blocked.detail.lower())


class ChatEndpointTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="chat-user", password="x")
        self.feed = Feed.objects.create(
            title="BBC",
            url="https://example.com/chat-feed.xml",
            site_url="https://www.bbc.com",
            kind=Feed.SourceKind.CURATED,
        )
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
        self.article = Article.objects.create(
            feed=self.feed,
            title="Summit ends",
            url="https://example.com/summit",
            summary="Leaders agreed on a draft.",
            published_at=self.now,
        )
        self.thread = StoryThread.objects.create(
            label="Summit",
            last_published_at=self.now,
        )
        self.article.story_thread = self.thread
        self.article.save(update_fields=["story_thread", "updated_at"])
        self.client.force_login(self.user)

    def _post(self, payload: dict[str, Any]) -> Any:
        return self.client.post(
            reverse("chat"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _json(self, response: Any) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(response.content.decode("utf-8")))

    @patch("news.views.invoke_news_chat")
    def test_brief_chat_ok(self, mock_invoke) -> None:
        mock_invoke.return_value = ChatWorkerResponse(
            refused=False,
            reason="ok",
            reply="They agreed on a draft.",
        )
        response = self._post({"scope": "brief", "message": "What happened?", "history": []})
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertTrue(data["ok"])
        self.assertFalse(data["refused"])
        self.assertIn("draft", data["reply"])
        mock_invoke.assert_called_once()
        req = mock_invoke.call_args[0][0]
        self.assertEqual(req.scope, "brief")
        self.assertTrue(any(c.title == "Summit ends" for c in req.chunks))

    @patch("news.views.invoke_news_chat")
    def test_refuse_path(self, mock_invoke) -> None:
        mock_invoke.return_value = ChatWorkerResponse(
            refused=True,
            reason="off_topic",
            message="I can only help with this news context.",
        )
        response = self._post({"scope": "brief", "message": "Write a poem", "history": []})
        self.assertEqual(response.status_code, 200)
        data = self._json(response)
        self.assertTrue(data["ok"])
        self.assertTrue(data["refused"])
        self.assertEqual(data["reason"], "off_topic")

    @patch("news.views.invoke_news_chat")
    def test_thread_out_of_scope_404(self, mock_invoke) -> None:
        other = Feed.objects.create(
            title="Other",
            url="https://example.com/other-chat.xml",
            kind=Feed.SourceKind.CURATED,
        )
        orphan = StoryThread.objects.create(label="Orphan", last_published_at=self.now)
        Article.objects.create(
            feed=other,
            title="Elsewhere",
            url="https://example.com/elsewhere",
            summary="Nope",
            published_at=self.now,
            story_thread=orphan,
        )
        # User has English catalog by default; mute BBC and don't subscribe to other
        # — enabled_feed_ids still includes curated unless muted. Mute both.
        from news.models import FeedMute

        FeedMute.objects.create(user=self.user, feed=self.feed)
        FeedMute.objects.create(user=self.user, feed=other)

        response = self._post(
            {
                "scope": "thread",
                "scope_id": orphan.id,
                "message": "What happened?",
                "history": [],
            }
        )
        self.assertEqual(response.status_code, 404)
        mock_invoke.assert_not_called()

    @patch("news.views.invoke_news_chat")
    def test_thread_chat_ok(self, mock_invoke) -> None:
        mock_invoke.return_value = ChatWorkerResponse(
            refused=False,
            reason="ok",
            reply="Thread summary.",
        )
        response = self._post(
            {
                "scope": "thread",
                "scope_id": self.thread.id,
                "message": "Summarize",
                "history": [],
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._json(response)["ok"])

    def test_message_cap(self) -> None:
        response = self._post(
            {
                "scope": "brief",
                "message": "x" * 2001,
                "history": [],
            }
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    @patch("news.views.invoke_news_chat")
    @patch("news.views.check_and_increment")
    def test_rate_limit_429(self, mock_rl, mock_invoke) -> None:
        from news.services.chat_rate_limit import RateLimitDecision

        mock_rl.return_value = RateLimitDecision(
            allowed=False,
            retry_after_seconds=30,
            detail="Too many chat messages this minute. Try again shortly.",
        )
        response = self._post({"scope": "brief", "message": "Hi", "history": []})
        mock_invoke.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "30")
        self.assertEqual(self._json(response)["code"], "rate_limited")

    def test_requires_login(self) -> None:
        self.client.logout()
        response = self._post({"scope": "brief", "message": "Hi", "history": []})
        self.assertIn(response.status_code, (302, 401, 403))


class ChatDayLimitTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="chat-day", password="x")

    @patch.object(chat_rate_limit, "MINUTE_LIMIT", 10_000)
    def test_day_limit(self) -> None:
        for _ in range(DAY_LIMIT):
            self.assertTrue(check_and_increment(self.user).allowed)
        blocked = check_and_increment(self.user)
        self.assertFalse(blocked.allowed)
        self.assertIn("daily", blocked.detail.lower())
