"""Primary content language prefs and UI locale activation."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.timezone import now

from news.models import Language, StoryThread, StoryThreadLocalization, UserContentLanguage
from news.services.feeds import (
    preferred_content_language_order,
    preferred_content_languages,
    primary_content_language,
    set_user_content_languages,
)
from news.services.thread_copy import resolve_thread_copy

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    # django-stubs types User.objects as Manager[AbstractBaseUser] without create_user.
    return cast(Any, User.objects).create_user(**kwargs)


def _ensure_languages() -> None:
    for code, name, order in (
        ("en", "English", 10),
        ("fr", "Français", 20),
        ("de", "Deutsch", 30),
    ):
        Language.objects.update_or_create(code=code, defaults={"name": name, "sort_order": order})


class PrimaryLanguageTests(TestCase):
    def setUp(self) -> None:
        _ensure_languages()
        self.user = _create_user(username="lang-user", password="x")

    def test_set_user_content_languages_marks_one_primary(self) -> None:
        set_user_content_languages(self.user, languages=["en", "de"], primary="de")
        self.assertEqual(primary_content_language(self.user), "de")
        self.assertEqual(
            UserContentLanguage.objects.filter(user=self.user, is_primary=True).count(),
            1,
        )
        self.assertEqual(
            preferred_content_language_order(self.user),
            ["de", "en"],
        )

    def test_primary_coerced_when_not_in_accept_set(self) -> None:
        set_user_content_languages(self.user, languages=["fr", "de"], primary="en")
        # en missing → first selected code.
        self.assertEqual(primary_content_language(self.user), "fr")
        self.assertEqual(preferred_content_languages(self.user), {"fr", "de"})

    def test_resolve_prefers_primary_localization(self) -> None:
        set_user_content_languages(self.user, languages=["en", "de"], primary="de")
        thread = StoryThread.objects.create(label="EN", last_published_at=now())
        StoryThreadLocalization.objects.create(
            story_thread=thread,
            language_id="en",
            label="English Label",
            summary="English summary.",
        )
        StoryThreadLocalization.objects.create(
            story_thread=thread,
            language_id="de",
            label="Deutsches Label",
            summary="Deutsche Zusammenfassung.",
        )
        copy = resolve_thread_copy(thread, preferred_content_language_order(self.user))
        self.assertEqual(copy.language, "de")
        self.assertEqual(copy.label, "Deutsches Label")

    def test_settings_save_primary(self) -> None:
        client = Client()
        client.force_login(self.user)
        response = client.post(
            reverse("settings"),
            {
                "save_languages": "1",
                "languages": ["en", "fr"],
                "primary": "fr",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(primary_content_language(self.user), "fr")
        self.assertEqual(
            preferred_content_language_order(self.user),
            ["fr", "en"],
        )


@override_settings(LANGUAGE_CODE="en")
class PrimaryLocaleMiddlewareTests(TestCase):
    def setUp(self) -> None:
        _ensure_languages()
        self.user = _create_user(username="locale-user", password="x")
        set_user_content_languages(self.user, languages=["en", "fr"], primary="fr")
        self.client = Client()

    def test_authenticated_request_activates_primary(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Language"), "fr")
        self.assertContains(response, "Paramètres")

    def test_guest_stays_english(self) -> None:
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Language"), "en")
        translation.deactivate()
