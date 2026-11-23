"""Tests for feed-scoped article title + embedding search."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from news.models import Article, Feed, FeedMute
from news.services.article_search import search_articles_for_user

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    return cast(Any, User.objects).create_user(**kwargs)


def _vec(seed: float) -> list[float]:
    values = [0.0] * 1024
    values[0] = seed
    values[1] = (1.0 - seed * seed) ** 0.5 if abs(seed) < 1 else 0.0
    return values


class ArticleSearchServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="search-user", password="x")
        self.feed = Feed.objects.create(
            title="BBC",
            url="https://example.com/search-feed.xml",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.other_feed = Feed.objects.create(
            title="Other",
            url="https://example.com/other-feed.xml",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
        self.in_scope = Article.objects.create(
            feed=self.feed,
            title="Floods hit coastal towns",
            url="https://example.com/floods",
            summary="Heavy rain overnight.",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )
        self.vector_match = Article.objects.create(
            feed=self.feed,
            title="Storm surge warnings",
            url="https://example.com/storm",
            summary="Officials urge caution.",
            published_at=self.now,
            embedding=_vec(0.99),
            embedding_model="test",
            embedded_at=self.now,
        )
        self.out_of_scope = Article.objects.create(
            feed=self.other_feed,
            title="Floods hit coastal towns",
            url="https://example.com/floods-other",
            summary="Same title elsewhere.",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )
        FeedMute.objects.create(user=self.user, feed=self.other_feed)

    def test_title_match_respects_feed_scope(self) -> None:
        chunks = search_articles_for_user(user=self.user, query="Floods hit coastal")
        ids = {c.article_id for c in chunks}
        self.assertIn(self.in_scope.pk, ids)
        self.assertNotIn(self.out_of_scope.pk, ids)

    def test_embedding_match_fills_results(self) -> None:
        chunks = search_articles_for_user(
            user=self.user,
            query="zzz-no-title-hit",
            embedding=_vec(1.0),
            limit=5,
        )
        ids = {c.article_id for c in chunks}
        self.assertIn(self.in_scope.pk, ids)
        self.assertIn(self.vector_match.pk, ids)
        self.assertNotIn(self.out_of_scope.pk, ids)

    def test_exclude_article_ids(self) -> None:
        chunks = search_articles_for_user(
            user=self.user,
            query="Floods",
            exclude_article_ids=[self.in_scope.pk],
        )
        ids = {c.article_id for c in chunks}
        self.assertNotIn(self.in_scope.pk, ids)


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class ArticleSearchApiTests(TestCase):
    def setUp(self) -> None:
        self.user = _create_user(username="search-api", password="x")
        self.feed = Feed.objects.create(
            title="BBC",
            url="https://example.com/search-api-feed.xml",
            kind=Feed.SourceKind.CURATED,
            language="en",
        )
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
        self.article = Article.objects.create(
            feed=self.feed,
            title="Climate summit closes",
            url="https://example.com/summit-api",
            summary="Draft text agreed.",
            published_at=self.now,
            embedding=_vec(1.0),
            embedding_model="test",
            embedded_at=self.now,
        )

    def _post(self, payload: dict[str, Any]) -> Any:
        return self.client.post(
            reverse("internal_search_articles"),
            data=json.dumps(payload),
            content_type="application/json",
            headers={"Authorization": "Bearer test-internal-token"},
        )

    def test_search_ok(self) -> None:
        response = self._post(
            {
                "query": "Climate summit",
                "user_id": self.user.pk,
                "limit": 5,
            }
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))
        titles = [row["title"] for row in data["results"]]
        self.assertIn("Climate summit closes", titles)

    def test_unknown_user_404(self) -> None:
        response = self._post({"query": "Climate", "user_id": 999_999})
        self.assertEqual(response.status_code, 404)

    def test_requires_token(self) -> None:
        response = self.client.post(
            reverse("internal_search_articles"),
            data=json.dumps({"query": "Climate", "user_id": self.user.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
