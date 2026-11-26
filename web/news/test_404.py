from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False, ROOT_URLCONF="config.urls")
class NotFoundPageTests(SimpleTestCase):
    def test_unknown_path_renders_custom_404(self) -> None:
        response = self.client.get("/this-page-definitely-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response,
            "Sorry, this page doesn’t exist.",
            status_code=404,
        )
        self.assertContains(response, "site-header", status_code=404)
        self.assertContains(response, "site-footer", status_code=404)
