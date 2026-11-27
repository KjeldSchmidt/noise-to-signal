"""Post-signup preference wizard helpers."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import HttpRequest
from django.utils import timezone

from news.models import Theme, UserOnboarding, UserThemeAffinity
from news.services.feeds import (
    DEFAULT_CONTENT_LANGUAGES,
    PRODUCT_THREAD_LANGUAGES,
    catalog_languages,
    set_user_content_languages,
)

MAX_ONBOARDING_LOCATIONS = 3
MAX_ONBOARDING_THEMES = 6

ONBOARDING_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/onboarding/",
    "/settings/",
    "/accounts/",
    "/admin/",
    "/api/",
    "/static/",
    "/privacy/",
    "/health",
    "/locations/",
    "/oauth/popup-done/",
)


def is_onboarding_complete(user: AbstractBaseUser | AnonymousUser) -> bool:
    """True when the user was never enrolled or has finished/skipped the wizard.

    Missing ``UserOnboarding`` rows mean legacy/test accounts (not enrolled).
    New signups get a pending row via the ``user_signed_up`` signal.
    """
    if not getattr(user, "is_authenticated", False):
        return True
    row = UserOnboarding.objects.filter(user_id=user.pk).only("completed_at").first()
    if row is None:
        return True
    return row.completed_at is not None


def enroll_onboarding(user: AbstractBaseUser) -> UserOnboarding:
    """Create a pending onboarding row for a brand-new signup (idempotent)."""
    row, _ = UserOnboarding.objects.get_or_create(user=user)
    return row


def mark_onboarding_complete(user: AbstractBaseUser) -> UserOnboarding:
    row, _ = UserOnboarding.objects.get_or_create(user=user)
    if row.completed_at is None:
        row.completed_at = timezone.now()
        row.save(update_fields=["completed_at", "updated_at"])
    return row


def parse_accept_language_codes(header: str) -> list[str]:
    """Extract BCP-47 language tags from an Accept-Language header, best-first."""
    if not header.strip():
        return []
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        token = part.strip()
        if not token:
            continue
        lang_part, _, params = token.partition(";")
        code = lang_part.strip().lower().replace("_", "-")
        if not code or code == "*":
            continue
        q = 1.0
        for param in params.split(";"):
            param = param.strip()
            if param.startswith("q="):
                try:
                    q = float(param[2:].strip())
                except ValueError:
                    q = 0.0
        ranked.append((q, -index, code))
    ranked.sort(reverse=True)
    return [code for _, _, code in ranked]


def match_catalog_languages(
    preferred_codes: list[str],
    *,
    catalog: list[str] | None = None,
) -> tuple[list[str], str]:
    """Map preferred browser codes onto the catalog; fall back to English."""
    available = catalog if catalog is not None else catalog_languages()
    if not available:
        available = list(DEFAULT_CONTENT_LANGUAGES)

    catalog_set = {code.lower() for code in available}
    selected: list[str] = []
    primary = ""

    for raw in preferred_codes:
        base = raw.split("-", 1)[0].lower()
        match = ""
        if raw.lower() in catalog_set:
            match = raw.lower()
        elif base in catalog_set:
            match = base
        if not match:
            continue
        if match not in selected:
            selected.append(match)
        if not primary:
            primary = match

    if not selected:
        selected = ["en"] if "en" in catalog_set else [available[0]]
        primary = selected[0]
    if primary not in selected:
        primary = selected[0]
    return selected, primary


def languages_from_request(
    request: HttpRequest,
    *,
    catalog: list[str] | None = None,
) -> tuple[list[str], str]:
    header = request.headers.get("Accept-Language", "") or ""
    return match_catalog_languages(parse_accept_language_codes(header), catalog=catalog)


def user_has_content_languages(user: AbstractBaseUser) -> bool:
    from news.models import UserContentLanguage

    return UserContentLanguage.objects.filter(user=user).exists()


def ensure_language_defaults(
    user: AbstractBaseUser,
    *,
    languages: list[str] | None = None,
    primary: str | None = None,
    catalog: list[str] | None = None,
) -> None:
    """Ensure a non-empty accept set; only writes when the user has no rows yet."""
    if user_has_content_languages(user):
        return
    if languages is None or primary is None:
        selected, primary_code = match_catalog_languages([], catalog=catalog)
    else:
        selected, primary_code = match_catalog_languages(
            [primary, *languages],
            catalog=catalog,
        )
        # Preserve caller order when codes are already catalog-valid.
        cleaned = [str(code).strip().lower() for code in languages if code]
        available = {
            c.lower() for c in (catalog or catalog_languages() or list(DEFAULT_CONTENT_LANGUAGES))
        }
        selected = [code for code in cleaned if code in available] or selected
        if primary_code not in selected:
            primary_code = selected[0]
    set_user_content_languages(user, languages=selected, primary=primary_code)


def seed_theme_interests(user: AbstractBaseUser, slugs: list[str]) -> int:
    """Seed more_count=1 for selected active themes (idempotent for existing rows)."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in slugs:
        slug = str(raw).strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        cleaned.append(slug)
        if len(cleaned) >= MAX_ONBOARDING_THEMES:
            break

    if not cleaned:
        return 0

    themes = {theme.slug: theme for theme in Theme.objects.filter(is_active=True, slug__in=cleaned)}
    created = 0
    for slug in cleaned:
        theme = themes.get(slug)
        if theme is None:
            continue
        _row, was_created = UserThemeAffinity.objects.get_or_create(
            user=user,
            theme=theme,
            defaults={"more_count": 1, "less_count": 0},
        )
        if was_created:
            created += 1
        elif _row.more_count == 0 and _row.less_count == 0:
            _row.more_count = 1
            _row.save(update_fields=["more_count", "updated_at"])
            created += 1
    return created


def finish_onboarding_with_language_defaults(
    user: AbstractBaseUser,
    *,
    request: HttpRequest | None = None,
) -> None:
    """Skip path: ensure languages from Accept-Language (or en), then mark complete."""
    catalog = catalog_languages() or list(PRODUCT_THREAD_LANGUAGES)
    if request is not None:
        langs, primary = languages_from_request(request, catalog=catalog)
    else:
        langs, primary = match_catalog_languages([], catalog=catalog)
    ensure_language_defaults(user, languages=langs, primary=primary, catalog=catalog)
    mark_onboarding_complete(user)
