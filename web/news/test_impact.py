"""Unit tests for shared impact scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from news.models import ImpactTier
from news.services.impact import (
    HALF_LIFE_HOURS,
    article_impact_score,
    blend_relevance_impact,
    tier_weight,
)


class ImpactScoreTests(SimpleTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)

    def test_tier_weights_order(self) -> None:
        self.assertGreater(tier_weight(ImpactTier.MAJOR), tier_weight(ImpactTier.NOTABLE))
        self.assertGreater(tier_weight(ImpactTier.NOTABLE), tier_weight(ImpactTier.EPHEMERAL))
        self.assertGreater(tier_weight(ImpactTier.EPHEMERAL), tier_weight(ImpactTier.COMMERCIAL))

    def test_half_life_halves_score(self) -> None:
        fresh = article_impact_score(ImpactTier.MAJOR, self.now, now=self.now)
        aged = article_impact_score(
            ImpactTier.MAJOR,
            self.now - timedelta(hours=HALF_LIFE_HOURS),
            now=self.now,
        )
        self.assertAlmostEqual(aged, fresh * 0.5, places=6)

    def test_blend_treats_missing_similarity_as_full_relevance(self) -> None:
        self.assertEqual(blend_relevance_impact(similarity=None, impact=2.5), 2.5)
        self.assertEqual(blend_relevance_impact(similarity=0.5, impact=2.0), 1.0)
