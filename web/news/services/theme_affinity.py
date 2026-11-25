"""User theme more/less counts and log-damped weights for brief ranking."""

from __future__ import annotations

import math
from typing import Literal

from django.contrib.auth.models import AbstractBaseUser

from news.models import Theme, UserThemeAffinity

AffinityDirection = Literal["more", "less"]
AffinityLean = Literal["more", "less", "neutral"]


def affinity_weight(more_count: int, less_count: int) -> float:
    """Log-damped lean: positive = more, negative = less."""
    return math.log1p(max(0, more_count)) - math.log1p(max(0, less_count))


def apply_theme_affinity_vote(
    user: AbstractBaseUser,
    *,
    theme_slug: str,
    direction: AffinityDirection,
    previous: AffinityLean = "neutral",
) -> UserThemeAffinity | None:
    """
    Apply a Reddit-style lean transition for an active theme.

    ``previous`` is the client's last lean for this article+theme (or neutral).
    Same-direction votes are no-ops. Flips undo the prior contribution then apply
    the new one so ▲→▼→▲→▼ matches a single final vote from neutral.
    Returns None if the theme slug is unknown/inactive.
    """
    if previous not in ("more", "less", "neutral"):
        raise ValueError("previous must be more, less, or neutral")
    if direction not in ("more", "less"):
        raise ValueError("direction must be more or less")

    theme = Theme.objects.filter(is_active=True, slug=theme_slug).first()
    if theme is None:
        return None

    affinity, _ = UserThemeAffinity.objects.get_or_create(user=user, theme=theme)
    if previous == direction:
        return affinity

    more = affinity.more_count
    less = affinity.less_count
    if previous == "neutral":
        if direction == "more":
            more += 1
        else:
            less += 1
    elif previous == "more" and direction == "less":
        more = max(0, more - 1)
        less += 1
    elif previous == "less" and direction == "more":
        less = max(0, less - 1)
        more += 1

    affinity.more_count = more
    affinity.less_count = less
    affinity.save(update_fields=["more_count", "less_count", "updated_at"])
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
