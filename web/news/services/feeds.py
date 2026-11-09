"""Feed enablement — catalog on by default; FeedMute is opt-out."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from news.models import Feed, FeedMute


def catalog_feeds() -> QuerySet[Feed]:
    return Feed.objects.filter(
        is_active=True,
        owner__isnull=True,
        kind__in=[Feed.SourceKind.CURATED, Feed.SourceKind.RECOMMENDED],
    )


def catalog_feed_ids() -> list[int]:
    """Active curated/recommended catalog feeds (no personalization)."""
    return sorted(catalog_feeds().values_list("id", flat=True))


def enabled_feed_ids(user: AbstractBaseUser) -> list[int]:
    """Active catalog feeds minus mutes, plus the user's active custom feeds (unless muted)."""
    muted = set(FeedMute.objects.filter(user=user).values_list("feed_id", flat=True))
    catalog_ids = set(catalog_feeds().values_list("id", flat=True))
    custom_ids = set(
        Feed.objects.filter(owner=user, is_active=True).values_list("id", flat=True)
    )
    return sorted((catalog_ids | custom_ids) - muted)
