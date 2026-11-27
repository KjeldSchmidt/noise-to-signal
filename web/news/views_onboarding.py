"""Post-signup preference wizard (languages → places → themes)."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from news.forms import ContentLanguagesForm, LocationOfInterestForm
from news.models import LocationOfInterest, Theme
from news.services.feeds import (
    PRODUCT_THREAD_LANGUAGES,
    catalog_languages,
    preferred_content_languages,
    primary_content_language,
    set_user_content_languages,
)
from news.services.onboarding import (
    MAX_ONBOARDING_LOCATIONS,
    ensure_language_defaults,
    finish_onboarding_with_language_defaults,
    is_onboarding_complete,
    languages_from_request,
    mark_onboarding_complete,
    seed_theme_interests,
    user_has_content_languages,
)


def _user(request: HttpRequest) -> AbstractBaseUser:
    return cast(AbstractBaseUser, request.user)


def _available_languages() -> list[str]:
    """Prefer languages on catalog feeds; fall back to the product UI set."""
    catalog = catalog_languages()
    if catalog:
        return catalog
    return list(PRODUCT_THREAD_LANGUAGES)


def _language_initial(request: HttpRequest, user: AbstractBaseUser) -> dict[str, object]:
    catalog = _available_languages()
    if user_has_content_languages(user):
        return {
            "languages": sorted(preferred_content_languages(user)),
            "primary": primary_content_language(user),
        }
    langs, primary = languages_from_request(request, catalog=catalog)
    return {"languages": langs, "primary": primary}


def _handle_skip(request: HttpRequest) -> HttpResponse | None:
    if request.method == "POST" and "skip_onboarding" in request.POST:
        finish_onboarding_with_language_defaults(_user(request), request=request)
        return redirect("brief")
    return None


@login_required
def onboarding_entry(request: HttpRequest) -> HttpResponse:
    if is_onboarding_complete(_user(request)):
        return redirect("brief")
    return redirect("onboarding_languages")


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_languages(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    if is_onboarding_complete(user):
        return redirect("brief")

    skipped = _handle_skip(request)
    if skipped is not None:
        return skipped

    available = _available_languages()
    form = ContentLanguagesForm(
        available=available,
        initial=_language_initial(request, user),
    )

    if request.method == "POST" and "save_languages" in request.POST:
        form = ContentLanguagesForm(request.POST, available=available)
        if form.is_valid():
            set_user_content_languages(
                user,
                languages=list(form.cleaned_data["languages"]),
                primary=str(form.cleaned_data["primary"]),
            )
            return redirect("onboarding_places")

    return render(
        request,
        "news/onboarding/languages.html",
        {
            "step": 1,
            "step_count": 3,
            "form": form,
            "prefill_from_browser": not user_has_content_languages(user),
            "catalog_languages": available,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_places(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    if is_onboarding_complete(user):
        return redirect("brief")

    skipped = _handle_skip(request)
    if skipped is not None:
        return skipped

    # Languages should exist before places; heal empty accept sets.
    langs, primary = languages_from_request(request, catalog=_available_languages())
    ensure_language_defaults(
        user,
        languages=langs,
        primary=primary,
        catalog=_available_languages(),
    )

    locations = list(LocationOfInterest.objects.filter(user=user).order_by("label", "id"))
    location_form = LocationOfInterestForm()
    at_cap = len(locations) >= MAX_ONBOARDING_LOCATIONS

    if request.method == "POST" and "continue_places" in request.POST:
        return redirect("onboarding_themes")

    if request.method == "POST" and "skip_step" in request.POST:
        return redirect("onboarding_themes")

    if request.method == "POST" and "add_location" in request.POST:
        if at_cap:
            location_form = LocationOfInterestForm()
        else:
            location_form = LocationOfInterestForm(request.POST)
            if location_form.is_valid():
                loc = location_form.save(commit=False)
                loc.user = user
                loc.save()
                return redirect("onboarding_places")

    return render(
        request,
        "news/onboarding/places.html",
        {
            "step": 2,
            "step_count": 3,
            "locations": locations,
            "location_form": location_form,
            "at_cap": at_cap,
            "max_locations": MAX_ONBOARDING_LOCATIONS,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_themes(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    if is_onboarding_complete(user):
        return redirect("brief")

    skipped = _handle_skip(request)
    if skipped is not None:
        return skipped

    langs, primary = languages_from_request(request, catalog=_available_languages())
    ensure_language_defaults(
        user,
        languages=langs,
        primary=primary,
        catalog=_available_languages(),
    )

    themes = list(Theme.objects.filter(is_active=True).order_by("sort_order", "slug"))

    if request.method == "POST" and ("save_themes" in request.POST or "skip_step" in request.POST):
        if "save_themes" in request.POST:
            slugs = [str(s) for s in request.POST.getlist("themes")]
            seed_theme_interests(user, slugs)
        mark_onboarding_complete(user)
        return redirect("brief")

    return render(
        request,
        "news/onboarding/themes.html",
        {
            "step": 3,
            "step_count": 3,
            "themes": themes,
        },
    )


def post_auth_next_url(request: HttpRequest, fallback: str | None = None) -> str:
    """Resolve OAuth `next` — incomplete onboarding always wins."""
    user = _user(request)
    if not is_onboarding_complete(user):
        return reverse("onboarding")
    return fallback or reverse("brief")
