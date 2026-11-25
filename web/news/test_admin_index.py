"""Admin index lists custom pages; all news models are registered."""

from __future__ import annotations

from typing import Any, cast

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from news.admin_custom_pages import iter_custom_admin_pages

UserModel = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    return cast(Any, UserModel.objects).create_user(**kwargs)


class AdminIndexCustomPagesTests(TestCase):
    def setUp(self) -> None:
        self.staff = _create_user(
            username="admin-index-staff",
            password="x",
            is_staff=True,
        )
        self.index_url = reverse("admin:index")

    def test_custom_pages_registered(self) -> None:
        pages = iter_custom_admin_pages()
        self.assertGreaterEqual(len(pages), 2)
        names = {p.name for p in pages}
        self.assertIn("news_ops", names)
        self.assertIn("news_theme_analysis", names)

    def test_index_lists_every_custom_page(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 200)
        pages = iter_custom_admin_pages()
        self.assertTrue(pages)
        for page in pages:
            with self.subTest(page=page.name):
                self.assertContains(response, page.title)
                self.assertContains(response, reverse(f"admin:{page.name}"))

    def test_sidebar_lists_every_custom_page(self) -> None:
        """Non-index admin pages include Tools links in the left nav."""
        self.client.force_login(self.staff)
        # Ops is staff-accessible; index clears nav-sidebar so use another admin page.
        response = self.client.get(reverse("admin:news_ops"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="custom-admin-pages-nav"')
        pages = iter_custom_admin_pages()
        self.assertTrue(pages)
        for page in pages:
            with self.subTest(page=page.name):
                self.assertContains(response, page.title)
                self.assertContains(response, reverse(f"admin:{page.name}"))


class AdminModelRegistrationTests(TestCase):
    def test_all_concrete_news_models_registered(self) -> None:
        missing = [
            model._meta.label
            for model in apps.get_app_config("news").get_models()
            if model not in admin.site._registry
        ]
        self.assertEqual(
            missing,
            [],
            f"Register missing news models in news.admin: {missing}",
        )
