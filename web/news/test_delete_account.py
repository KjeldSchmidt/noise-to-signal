from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from news.models import Feed, Subscription

UserModel = cast(Any, get_user_model())


class DeleteAccountViewTests(TestCase):
    def setUp(self) -> None:
        self.user = UserModel.objects.create_user(
            username="deleteme",
            email="deleteme@example.com",
            password="x",
        )
        self.url = reverse("delete_account")

    def test_requires_login(self) -> None:
        response = self.client.post(self.url, {"confirm": "delete"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_missing_confirm_keeps_user(self) -> None:
        self.client.force_login(self.user)
        with patch(
            "news.views.erase_preference_memories",
            return_value=True,
        ) as erase:
            response = self.client.post(self.url, {})
        erase.assert_not_called()
        self.assertRedirects(response, reverse("settings"))
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_erase_failure_keeps_user(self) -> None:
        self.client.force_login(self.user)
        with patch(
            "news.views.erase_preference_memories",
            return_value=False,
        ) as erase:
            response = self.client.post(self.url, {"confirm": "delete"})
        erase.assert_called_once_with(self.user.pk)
        self.assertRedirects(response, reverse("settings"))
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_confirmed_delete_removes_user_and_session(self) -> None:
        self.client.force_login(self.user)
        with patch(
            "news.views.erase_preference_memories",
            return_value=True,
        ) as erase:
            response = self.client.post(self.url, {"confirm": "delete"})
        erase.assert_called_once_with(self.user.pk)
        self.assertRedirects(response, reverse("landing"))
        self.assertFalse(UserModel.objects.filter(pk=self.user.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)


class FeedOwnerSetNullOnUserDeleteTests(TestCase):
    def test_deleting_owner_leaves_shared_custom_feed(self) -> None:
        owner = UserModel.objects.create_user(username="owner", password="x")
        subscriber = UserModel.objects.create_user(username="sub", password="x")
        feed = Feed.objects.create(
            title="Shared niche",
            url="https://example.com/shared-custom.xml",
            kind=Feed.SourceKind.CUSTOM,
            language_id="und",
            owner=owner,
        )
        Subscription.objects.create(user=subscriber, feed=feed)

        owner.delete()

        feed.refresh_from_db()
        self.assertIsNone(feed.owner_id)
        self.assertTrue(Subscription.objects.filter(user=subscriber, feed=feed).exists())
