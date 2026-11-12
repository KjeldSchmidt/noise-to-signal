"""Postgres-backed per-user chat rate limits (shared across Lambda instances)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from news.models import ChatRateLimitBucket

MINUTE_LIMIT = 10
DAY_LIMIT = 100
MINUTE_BUCKET = "minute"
DAY_BUCKET = "day"
_PRUNE_RETENTION = timedelta(days=2)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    detail: str = ""


def _floor_minute(now: datetime) -> datetime:
    return now.replace(second=0, microsecond=0)


def _floor_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _increment(
    user: AbstractBaseUser,
    bucket_key: str,
    window_start: datetime,
) -> int:
    """Atomically upsert and increment; return the new count."""
    with transaction.atomic():
        bucket, _created = ChatRateLimitBucket.objects.select_for_update().get_or_create(
            user_id=user.pk,
            bucket_key=bucket_key,
            window_start=window_start,
            defaults={"count": 0},
        )
        ChatRateLimitBucket.objects.filter(pk=bucket.pk).update(
            count=F("count") + 1,
            updated_at=timezone.now(),
        )
        bucket.refresh_from_db(fields=["count"])
        return int(bucket.count)


def _prune_old_windows(*, now: datetime) -> None:
    cutoff = now - _PRUNE_RETENTION
    ChatRateLimitBucket.objects.filter(window_start__lt=cutoff).delete()


def check_and_increment(user: AbstractBaseUser) -> RateLimitDecision:
    """
    Consume one chat request against minute + day buckets.

    Returns allowed=False with retry hint when either window is exhausted.
    """
    now = timezone.now()
    _prune_old_windows(now=now)

    minute_start = _floor_minute(now)
    day_start = _floor_day(now)

    minute_count = _increment(user, MINUTE_BUCKET, minute_start)
    if minute_count > MINUTE_LIMIT:
        retry = int((minute_start + timedelta(minutes=1) - now).total_seconds())
        return RateLimitDecision(
            allowed=False,
            retry_after_seconds=max(retry, 1),
            detail="Too many chat messages this minute. Try again shortly.",
        )

    day_count = _increment(user, DAY_BUCKET, day_start)
    if day_count > DAY_LIMIT:
        tomorrow = day_start + timedelta(days=1)
        retry = int((tomorrow - now).total_seconds())
        return RateLimitDecision(
            allowed=False,
            retry_after_seconds=max(retry, 1),
            detail="Daily chat limit reached. Come back tomorrow.",
        )

    return RateLimitDecision(allowed=True)
