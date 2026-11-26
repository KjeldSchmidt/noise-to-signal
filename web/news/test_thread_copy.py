"""Tests for multilingual story-thread display resolution."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from news.models import Language, StoryThread, StoryThreadLocalization
from news.services.thread_copy import resolve_thread_copy, upsert_thread_localizations


class ThreadCopyResolveTests(TestCase):
    def setUp(self) -> None:
        for code, name, order in (
            ("en", "English", 10),
            ("fr", "Français", 20),
            ("de", "Deutsch", 30),
        ):
            Language.objects.update_or_create(
                code=code, defaults={"name": name, "sort_order": order}
            )
        self.thread = StoryThread.objects.create(
            label="English Label",
            summary="English summary.",
            last_published_at=timezone.now(),
        )
        StoryThreadLocalization.objects.create(
            story_thread=self.thread,
            language_id="en",
            label="English Label",
            summary="English summary.",
        )
        StoryThreadLocalization.objects.create(
            story_thread=self.thread,
            language_id="de",
            label="Deutsches Label",
            summary="Deutsche Zusammenfassung.",
        )
        StoryThreadLocalization.objects.create(
            story_thread=self.thread,
            language_id="fr",
            label="Libellé français",
            summary="Résumé français.",
        )

    def test_prefers_requested_language(self) -> None:
        copy = resolve_thread_copy(self.thread, ["de", "en"])
        self.assertEqual(copy.language, "de")
        self.assertEqual(copy.label, "Deutsches Label")
        self.assertIn("Deutsche", copy.summary)

    def test_falls_back_to_en(self) -> None:
        copy = resolve_thread_copy(self.thread, ["es"])
        self.assertEqual(copy.language, "en")
        self.assertEqual(copy.label, "English Label")

    def test_fallback_title_when_empty(self) -> None:
        empty = StoryThread.objects.create(
            label="",
            summary="",
            last_published_at=timezone.now(),
        )
        copy = resolve_thread_copy(empty, ["de"], fallback_title="Lead headline")
        self.assertEqual(copy.label, "Lead headline")
        self.assertEqual(copy.summary, "")


class ThreadCopyUpsertTests(TestCase):
    def setUp(self) -> None:
        for code, name, order in (
            ("en", "English", 10),
            ("fr", "Français", 20),
            ("de", "Deutsch", 30),
        ):
            Language.objects.update_or_create(
                code=code, defaults={"name": name, "sort_order": order}
            )
        self.thread = StoryThread.objects.create(
            label="",
            last_published_at=timezone.now(),
        )

    def test_upsert_mirrors_english(self) -> None:
        thread, written = upsert_thread_localizations(
            self.thread,
            [
                {"language": "en", "label": "Rail Crash", "summary": "A train derailed."},
                {
                    "language": "fr",
                    "label": "Accident ferroviaire",
                    "summary": "Un train a déraillé.",
                },
                {"language": "de", "label": "Zugunglück", "summary": "Ein Zug entgleiste."},
            ],
        )
        self.assertEqual(written, 3)
        self.assertEqual(thread.label, "Rail Crash")
        self.assertEqual(thread.summary, "A train derailed.")
        from news.services.thread_copy import localization_count

        self.assertEqual(localization_count(thread), 3)
