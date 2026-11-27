"""Post-signup preference wizard."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from news.models import Language, LocationOfInterest, Theme, UserContentLanguage, UserThemeAffinity
from news.services.onboarding import (
    enroll_onboarding,
    finish_onboarding_with_language_defaults,
    is_onboarding_complete,
    match_catalog_languages,
    parse_accept_language_codes,
    seed_theme_interests,
)

User = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    return cast(Any, User.objects).create_user(**kwargs)


def _ensure_languages() -> None:
    for code, name, order in (
        ("en", "English", 10),
        ("fr", "Français", 20),
        ("de", "Deutsch", 30),
    ):
        Language.objects.update_or_create(code=code, defaults={"name": name, "sort_order": order})


class AcceptLanguageParsingTests(TestCase):
    def test_parse_ordered_by_q(self) -> None:
        codes = parse_accept_language_codes("fr-FR,fr;q=0.9,en;q=0.8,de;q=0.7")
        self.assertEqual(codes[0], "fr-fr")
        self.assertIn("en", codes)
        self.assertIn("de", codes)

    def test_match_catalog_prefers_primary_browser_lang(self) -> None:
        selected, primary = match_catalog_languages(
            ["de-DE", "en-US"],
            catalog=["en", "fr", "de"],
        )
        self.assertEqual(primary, "de")
        self.assertEqual(selected, ["de", "en"])

    def test_match_falls_back_to_en(self) -> None:
        selected, primary = match_catalog_languages(["es-ES"], catalog=["en", "fr", "de"])
        self.assertEqual(selected, ["en"])
        self.assertEqual(primary, "en")


class OnboardingServiceTests(TestCase):
    def setUp(self) -> None:
        _ensure_languages()
        self.user = _create_user(username="ob-user", password="x")

    def test_unenrolled_user_is_complete(self) -> None:
        self.assertTrue(is_onboarding_complete(self.user))

    def test_enrolled_pending_is_incomplete(self) -> None:
        enroll_onboarding(self.user)
        self.assertFalse(is_onboarding_complete(self.user))

    def test_seed_theme_interests(self) -> None:
        tech, _ = Theme.objects.update_or_create(
            slug="tech", defaults={"label": "Technology", "sort_order": 1, "is_active": True}
        )
        Theme.objects.update_or_create(
            slug="policy", defaults={"label": "Policy", "sort_order": 99, "is_active": False}
        )
        created = seed_theme_interests(self.user, [tech.slug, "policy", tech.slug, "missing"])
        self.assertEqual(created, 1)
        row = UserThemeAffinity.objects.get(user=self.user, theme__slug="tech")
        self.assertEqual(row.more_count, 1)
        self.assertFalse(
            UserThemeAffinity.objects.filter(user=self.user, theme__slug="policy").exists()
        )

    def test_finish_skip_sets_languages_and_complete(self) -> None:
        enroll_onboarding(self.user)
        finish_onboarding_with_language_defaults(self.user)
        self.assertTrue(is_onboarding_complete(self.user))
        self.assertTrue(
            UserContentLanguage.objects.filter(user=self.user, language_id="en").exists()
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class OnboardingFlowTests(TestCase):
    def setUp(self) -> None:
        _ensure_languages()
        self.user = _create_user(username="flow-user", password="x")
        enroll_onboarding(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_incomplete_user_redirected_from_brief(self) -> None:
        response = self.client.get(reverse("brief"))
        self.assertRedirects(response, reverse("onboarding"), fetch_redirect_response=False)

    def test_onboarding_entry_redirects_to_languages(self) -> None:
        response = self.client.get(reverse("onboarding"))
        self.assertRedirects(response, reverse("onboarding_languages"))

    def test_save_languages_continues_to_places(self) -> None:
        response = self.client.post(
            reverse("onboarding_languages"),
            {"languages": ["en", "de"], "primary": "de", "save_languages": "1"},
        )
        self.assertRedirects(response, reverse("onboarding_places"))
        self.assertEqual(
            set(
                UserContentLanguage.objects.filter(user=self.user).values_list(
                    "language_id", flat=True
                )
            ),
            {"en", "de"},
        )
        self.assertTrue(
            UserContentLanguage.objects.filter(
                user=self.user, language_id="de", is_primary=True
            ).exists()
        )

    def test_languages_prefill_from_accept_language(self) -> None:
        response = self.client.get(
            reverse("onboarding_languages"),
            HTTP_ACCEPT_LANGUAGE="fr-FR,fr;q=0.9,en;q=0.8",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["primary"], "fr")
        self.assertIn("fr", form.initial["languages"])

    def test_skip_for_now_completes_with_defaults(self) -> None:
        response = self.client.post(
            reverse("onboarding_languages"),
            {"skip_onboarding": "1"},
            HTTP_ACCEPT_LANGUAGE="de,en;q=0.5",
        )
        self.assertRedirects(response, reverse("brief"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(is_onboarding_complete(self.user))
        langs = set(
            UserContentLanguage.objects.filter(user=self.user).values_list("language_id", flat=True)
        )
        self.assertTrue(langs)
        self.assertIn("de", langs)

    def test_add_location_and_finish_themes(self) -> None:
        Theme.objects.update_or_create(
            slug="tech", defaults={"label": "Technology", "sort_order": 1, "is_active": True}
        )
        Theme.objects.update_or_create(
            slug="climate", defaults={"label": "Climate", "sort_order": 2, "is_active": True}
        )

        self.client.post(
            reverse("onboarding_languages"),
            {"languages": ["en"], "primary": "en", "save_languages": "1"},
        )
        response = self.client.post(
            reverse("onboarding_places"),
            {
                "add_location": "1",
                "label": "Berlin, Germany",
                "latitude": "52.52",
                "longitude": "13.405",
                "country_code": "DE",
                "admin1": "Berlin",
                "locality": "Berlin",
                "geo_level": "locality",
            },
        )
        self.assertRedirects(response, reverse("onboarding_places"))
        self.assertEqual(LocationOfInterest.objects.filter(user=self.user).count(), 1)

        response = self.client.post(
            reverse("onboarding_themes"),
            {"themes": ["tech", "climate"], "save_themes": "1"},
        )
        self.assertRedirects(response, reverse("brief"), fetch_redirect_response=False)
        self.assertTrue(is_onboarding_complete(self.user))
        self.assertEqual(
            UserThemeAffinity.objects.filter(user=self.user, more_count=1).count(),
            2,
        )

    def test_completed_user_skips_wizard(self) -> None:
        from news.services.onboarding import mark_onboarding_complete

        mark_onboarding_complete(self.user)
        response = self.client.get(reverse("onboarding"))
        self.assertRedirects(response, reverse("brief"), fetch_redirect_response=False)

    def test_oauth_popup_done_points_to_onboarding(self) -> None:
        response = self.client.get(reverse("oauth_popup_done"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("onboarding"))
