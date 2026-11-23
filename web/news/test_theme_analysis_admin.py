"""Tests for theme analysis admin page."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

UserModel = get_user_model()


def _create_user(**kwargs: Any) -> Any:
    # django-stubs types User.objects as Manager[AbstractBaseUser] without create_user.
    return cast(Any, UserModel.objects).create_user(**kwargs)


class ThemeAnalysisAdminTests(TestCase):
    def setUp(self) -> None:
        self.staff = _create_user(
            username="theme-staff",
            password="x",
            is_staff=True,
        )
        self.url = reverse("admin:news_theme_analysis")

    def test_requires_staff(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    @override_settings(THEME_ANALYSIS_FUNCTION_NAME="", ANALYSIS_ARTIFACTS_BUCKET="")
    def test_get_unconfigured(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not configured")

    @override_settings(
        THEME_ANALYSIS_FUNCTION_NAME="noise-to-signal-dev-theme_analysis",
        ANALYSIS_ARTIFACTS_BUCKET="noise-to-signal-dev-analysis",
    )
    @patch("news.admin_theme_analysis.load_latest", return_value=None)
    @patch(
        "news.admin_theme_analysis.load_status",
        return_value={"status": "ready", "started_at": "t0", "finished_at": "t1", "error": ""},
    )
    def test_get_configured_empty_report(self, _status, _latest) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Refresh analysis")
        self.assertContains(response, "ready")

    @override_settings(
        THEME_ANALYSIS_FUNCTION_NAME="noise-to-signal-dev-theme_analysis",
        ANALYSIS_ARTIFACTS_BUCKET="noise-to-signal-dev-analysis",
    )
    @patch("news.admin_theme_analysis.load_latest", return_value=None)
    @patch(
        "news.admin_theme_analysis.load_status",
        return_value={"status": "running", "started_at": "t0", "finished_at": None, "error": ""},
    )
    @patch("news.admin_theme_analysis.invoke_theme_analysis", return_value=True)
    @patch("news.admin_theme_analysis.mark_running")
    def test_post_refresh(self, mock_mark, mock_invoke, _status, _latest) -> None:
        self.client.force_login(self.staff)
        response = self.client.post(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        mock_mark.assert_called_once()
        mock_invoke.assert_called_once()
        self.assertContains(response, "Analysis started")
