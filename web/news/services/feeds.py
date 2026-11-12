"""Feed enablement — catalog on by default; FeedMute is opt-out; customs via Subscription."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, QuerySet

from news.models import Feed, FeedMute, Subscription, UserContentLanguage

DEFAULT_CONTENT_LANGUAGES: frozenset[str] = frozenset({"en"})
UNKNOWN_FEED_LANGUAGES: frozenset[str] = frozenset({"", "und"})

CONTENT_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
}


def catalog_feeds() -> QuerySet[Feed]:
    return Feed.objects.filter(
        is_active=True,
        owner__isnull=True,
        kind__in=[Feed.SourceKind.CURATED, Feed.SourceKind.RECOMMENDED],
    )


def catalog_feed_ids(*, languages: set[str] | None = None) -> list[int]:
    """Active curated/recommended catalog feeds, optionally language-filtered."""
    qs = catalog_feeds()
    if languages is not None:
        qs = qs.filter(language__in=languages)
    return sorted(qs.values_list("id", flat=True))


def preferred_content_languages(user: AbstractBaseUser | None) -> set[str]:
    """Languages the user wants to read; guests and unset prefs default to English."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set(DEFAULT_CONTENT_LANGUAGES)
    langs = set(UserContentLanguage.objects.filter(user=user).values_list("language", flat=True))
    return langs or set(DEFAULT_CONTENT_LANGUAGES)


def catalog_languages() -> list[str]:
    """Distinct languages present on active catalog feeds, stable order."""
    raw = (
        catalog_feeds()
        .exclude(language__in=list(UNKNOWN_FEED_LANGUAGES))
        .values_list("language", flat=True)
        .distinct()
    )
    known = sorted({str(code).strip().lower() for code in raw if code})
    # Prefer en, fr, de first when present, then any other codes alphabetically.
    preferred_order = ["en", "fr", "de"]
    ordered = [code for code in preferred_order if code in known]
    ordered.extend(code for code in known if code not in preferred_order)
    return ordered


def enabled_feed_ids(user: AbstractBaseUser) -> list[int]:
    """Catalog (language ∩ prefs − mutes) plus the user's subscribed custom feeds."""
    preferred = preferred_content_languages(user)
    muted = set(FeedMute.objects.filter(user=user).values_list("feed_id", flat=True))
    catalog_ids = set(catalog_feed_ids(languages=preferred)) - muted
    custom_ids = set(
        Subscription.objects.filter(
            user=user,
            feed__is_active=True,
            feed__kind=Feed.SourceKind.CUSTOM,
        )
        .filter(
            # Unknown language always included; known language must match prefs.
            feed__language__in=list(preferred | UNKNOWN_FEED_LANGUAGES)
        )
        .values_list("feed_id", flat=True)
    )
    return sorted(catalog_ids | custom_ids)


def feed_should_poll(*, kind: str, is_active: bool, subscription_count: int) -> bool:
    """Whether feed_consumer should fetch this feed URL."""
    if not is_active:
        return False
    if kind == Feed.SourceKind.CUSTOM:
        return subscription_count > 0
    return True


def feeds_for_list_api() -> list[Feed]:
    """All feeds annotated with subscription_count for internal list_feeds."""
    return list(Feed.objects.annotate(subscription_count=Count("subscriptions")).order_by("id"))
