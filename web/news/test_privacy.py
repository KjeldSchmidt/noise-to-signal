from django.test import SimpleTestCase
from django.urls import reverse


class PrivacyPageTests(SimpleTestCase):
    def test_privacy_page_is_public(self) -> None:
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preference memory")
        self.assertContains(response, "Amazon Bedrock AgentCore Memory")
        self.assertContains(response, "90 days")
        self.assertContains(response, "erased")
        self.assertContains(response, 'href="/settings/"')
        self.assertContains(response, 'href="/privacy/"')
