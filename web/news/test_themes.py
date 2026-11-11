from django.test import TestCase

from news.models import Theme, ThemeSuggestion
from news.services.themes import record_theme_suggestions


class ThemeSuggestionTests(TestCase):
    def test_record_increments_and_skips_active(self) -> None:
        Theme.objects.update_or_create(
            slug="sports",
            defaults={"label": "Sports", "is_active": True},
        )
        n = record_theme_suggestions(
            ["Sports", "war-crimes", "War Crimes"],
            example_title="Example",
        )
        self.assertEqual(n, 2)
        row = ThemeSuggestion.objects.get(raw="war-crimes")
        self.assertEqual(row.count, 2)
        self.assertEqual(row.last_example_title, "Example")
        self.assertFalse(ThemeSuggestion.objects.filter(raw="sports").exists())
