"""User theme more/less counts and log-damped weights for brief ranking."""

from __future__ import annotations

import math
from typing import Literal

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F

from news.models import Theme, UserThemeAffinity

AffinityDirection = Literal["more", "less"]


def affinity_weight(more_count: int, less_count: int) -> float:
    """Log-damped lean: positive = more, negative = less."""
    return math.log1p(max(0, more_count)) - math.log1p(max(0, less_count))


def bump_theme_affinity(
    user: AbstractBaseUser,
    *,
    theme_slug: str,
    direction: AffinityDirection,
) -> UserThemeAffinity | None:
    """Increment more_count or less_count for an active theme; None if unknown slug."""
    theme = Theme.objects.filter(is_active=True, slug=theme_slug).first()
    if theme is None:
        return None
    affinity, _ = UserThemeAffinity.objects.get_or_create(user=user, theme=theme)
    if direction == "more":
        UserThemeAffinity.objects.filter(pk=affinity.pk).update(more_count=F("more_count") + 1)
    else:
        UserThemeAffinity.objects.filter(pk=affinity.pk).update(less_count=F("less_count") + 1)
    affinity.refresh_from_db()
    return affinity


def delete_theme_affinity(user: AbstractBaseUser, *, theme_slug: str) -> bool:
    deleted, _ = UserThemeAffinity.objects.filter(user=user, theme__slug=theme_slug).delete()
    return deleted > 0


def affinities_for_user(user: AbstractBaseUser) -> list[UserThemeAffinity]:
    return list(
        UserThemeAffinity.objects.filter(user=user)
        .select_related("theme")
        .order_by("theme__sort_order", "theme__slug")
    )


def weight_map_for_user(user: AbstractBaseUser) -> dict[str, float]:
    return {
        row.theme.slug: affinity_weight(row.more_count, row.less_count)
        for row in affinities_for_user(user)
        if row.theme_id
    }
