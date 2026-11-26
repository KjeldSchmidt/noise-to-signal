"""Feed enablement — catalog on by default; FeedMute is opt-out; customs via Subscription."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, QuerySet

from news.models import Feed, FeedMute, Language, Subscription, UserContentLanguage

DEFAULT_CONTENT_LANGUAGES: frozenset[str] = frozenset({"en"})
UNKNOWN_FEED_LANGUAGES: frozenset[str] = frozenset({"", "und"})
PRODUCT_THREAD_LANGUAGES: tuple[str, ...] = ("en", "fr", "de")

# Fallback labels when Language rows are missing (e.g. mid-migration).
_FALLBACK_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "und": "Unknown",
}


def content_language_labels() -> dict[str, str]:
    """code → display name from the Language catalog."""
    rows = list(Language.objects.order_by("sort_order", "code").values_list("code", "name"))
    if not rows:
        return dict(_FALLBACK_LANGUAGE_LABELS)
    return {code: name for code, name in rows}


# Back-compat alias used by templates/forms that expect a mapping.
CONTENT_LANGUAGE_LABELS: dict[str, str] = _FALLBACK_LANGUAGE_LABELS


def refresh_content_language_labels() -> dict[str, str]:
    """Reload module-level CONTENT_LANGUAGE_LABELS from DB (call after Language seeds)."""
    global CONTENT_LANGUAGE_LABELS
    CONTENT_LANGUAGE_LABELS = content_language_labels()
    return CONTENT_LANGUAGE_LABELS


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
        qs = qs.filter(language_id__in=languages)
    return sorted(qs.values_list("id", flat=True))


def preferred_content_languages(user: AbstractBaseUser | None) -> set[str]:
    """Languages the user wants to read; guests and unset prefs default to English."""
    if user is None or not getattr(user, "is_authenticated", False):
        return set(DEFAULT_CONTENT_LANGUAGES)
    langs = set(UserContentLanguage.objects.filter(user=user).values_list("language_id", flat=True))
    return langs or set(DEFAULT_CONTENT_LANGUAGES)


def preferred_content_language_order(user: AbstractBaseUser | None) -> list[str]:
    """Stable preference order for display resolution (product order, then extras)."""
    preferred = preferred_content_languages(user)
    ordered = [code for code in PRODUCT_THREAD_LANGUAGES if code in preferred]
    ordered.extend(sorted(code for code in preferred if code not in PRODUCT_THREAD_LANGUAGES))
    return ordered or list(DEFAULT_CONTENT_LANGUAGES)


def catalog_languages() -> list[str]:
    """Distinct languages present on active catalog feeds, stable order."""
    raw = (
        catalog_feeds()
        .exclude(language_id__in=list(UNKNOWN_FEED_LANGUAGES))
        .values_list("language_id", flat=True)
        .distinct()
    )
    known = sorted({str(code).strip().lower() for code in raw if code})
    preferred_order = list(PRODUCT_THREAD_LANGUAGES)
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
            feed__language_id__in=list(preferred | UNKNOWN_FEED_LANGUAGES)
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
