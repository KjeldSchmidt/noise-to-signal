"""Tests for internal article embeddings export API."""

from __future__ import annotations

from datetime import UTC, datetime

from django.test import TestCase, override_settings
from n2s_api import decode_embedding_f32_b64

from news.models import Article, Feed, Theme


def _vec(fill: float = 0.0) -> list[float]:
    out = [0.0] * 1024
    out[0] = fill
    return out


@override_settings(INTERNAL_API_TOKEN="test-internal-token")
class EmbeddingsExportApiTests(TestCase):
    def setUp(self) -> None:
        self.feed = Feed.objects.create(
            title="Export Feed",
            url="https://example.com/export.xml",
            kind=Feed.SourceKind.CURATED,
        )
        self.theme_tech, _ = Theme.objects.update_or_create(
            slug="tech",
            defaults={"label": "Tech", "sort_order": 1, "is_active": True},
        )
        self.theme_sports, _ = Theme.objects.update_or_create(
            slug="sports",
            defaults={"label": "Sports", "sort_order": 2, "is_active": True},
        )

    def _auth_get(self, path: str):
        return self.client.get(
            path,
            headers={"Authorization": "Bearer test-internal-token"},
        )

    def test_requires_token(self) -> None:
        response = self.client.get("/api/internal/articles/embeddings/")
        self.assertIn(response.status_code, {401, 403, 503})

    def test_export_paginates_and_encodes(self) -> None:
        a1 = Article.objects.create(
            feed=self.feed,
            title="One",
            url="https://example.com/1",
            summary="",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            embedding=_vec(1.0),
            embedding_model="test",
        )
        a1.themes.set([self.theme_sports, self.theme_tech])
        a2 = Article.objects.create(
            feed=self.feed,
            title="Two",
            url="https://example.com/2",
            summary="",
            published_at=datetime(2026, 1, 2, tzinfo=UTC),
            embedding=_vec(0.5),
            embedding_model="test",
        )
        a2.themes.set([self.theme_sports])
        Article.objects.create(
            feed=self.feed,
            title="No emb",
            url="https://example.com/3",
            summary="",
            published_at=datetime(2026, 1, 3, tzinfo=UTC),
        )

        page1 = self._auth_get("/api/internal/articles/embeddings/?limit=1")
        self.assertEqual(page1.status_code, 200)
        payload = page1.json()
        self.assertEqual(len(payload["articles"]), 1)
        self.assertEqual(payload["articles"][0]["id"], a1.id)
        self.assertEqual(payload["articles"][0]["theme_slugs"], ["tech", "sports"])
        decoded = decode_embedding_f32_b64(payload["articles"][0]["embedding_b64"])
        self.assertEqual(len(decoded), 1024)
        self.assertAlmostEqual(decoded[0], 1.0, places=5)
        self.assertEqual(payload["next_cursor"], a1.id)

        page2 = self._auth_get(f"/api/internal/articles/embeddings/?cursor={a1.id}&limit=10")
        self.assertEqual(page2.status_code, 200)
        payload2 = page2.json()
        self.assertEqual([row["id"] for row in payload2["articles"]], [a2.id])
        self.assertIsNone(payload2["next_cursor"])

    def test_invalid_limit(self) -> None:
        response = self._auth_get("/api/internal/articles/embeddings/?limit=9999")
        self.assertEqual(response.status_code, 400)
