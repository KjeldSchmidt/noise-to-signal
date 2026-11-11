"""Theme suggestion counters for extract free-form rejects."""

from __future__ import annotations

import re

from django.db.models import F
from django.utils import timezone

from news.models import Theme, ThemeSuggestion


def normalize_theme_suggestion(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:64]


def record_theme_suggestions(
    suggestions: list[str],
    *,
    example_title: str = "",
) -> int:
    """Increment counters for non-allowlisted suggestions. Returns rows touched."""
    if not suggestions:
        return 0
    active = set(Theme.objects.filter(is_active=True).values_list("slug", flat=True))
    title = (example_title or "")[:300]
    touched = 0
    now = timezone.now()
    for raw in suggestions:
        key = normalize_theme_suggestion(raw)
        if not key or key in active:
            continue
        obj, created = ThemeSuggestion.objects.get_or_create(
            raw=key,
            defaults={
                "count": 1,
                "last_seen_at": now,
                "last_example_title": title,
            },
        )
        if created:
            touched += 1
            continue
        ThemeSuggestion.objects.filter(pk=obj.pk).update(
            count=F("count") + 1,
            last_seen_at=now,
            last_example_title=title,
        )
        touched += 1
    return touched
