from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class NewsOpsAdminTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="ops-staff",
            password="x",
            is_staff=True,
        )
        self.ops_url = reverse("admin:news_ops")

    def test_ops_requires_staff(self) -> None:
        response = self.client.get(self.ops_url)
        self.assertEqual(response.status_code, 302)

    def test_ops_get_ok_for_staff(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.ops_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dissolve singleton threads")
        self.assertContains(response, "Reconcile story threads")
        self.assertContains(response, "Requeue articles")

    @patch("news.admin_ops.dissolve_singleton_threads", return_value=(2, 3))
    def test_ops_dissolve_posts(self, mock_dissolve) -> None:
        self.client.force_login(self.staff)
        response = self.client.post(self.ops_url, {"action": "dissolve"}, follow=True)
        self.assertEqual(response.status_code, 200)
        mock_dissolve.assert_called_once()
        self.assertContains(response, "cleared 2 article")
