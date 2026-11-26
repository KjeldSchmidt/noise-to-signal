# Language catalog, FK language columns, StoryThreadLocalization + en backfill.

from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

LANGUAGE_SEED: list[tuple[str, str, int]] = [
    ("en", "English", 10),
    ("fr", "Français", 20),
    ("de", "Deutsch", 30),
    ("und", "Unknown", 90),
]


def seed_languages(apps, schema_editor) -> None:
    Language = apps.get_model("news", "Language")
    now = django.utils.timezone.now()
    for code, name, sort_order in LANGUAGE_SEED:
        Language.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "created_at": now,
                "updated_at": now,
            },
        )


def ensure_language_codes(apps, schema_editor) -> None:
    """Any feed/pref code not in the seed gets a placeholder Language row."""
    Language = apps.get_model("news", "Language")
    Feed = apps.get_model("news", "Feed")
    UserContentLanguage = apps.get_model("news", "UserContentLanguage")
    now = django.utils.timezone.now()
    codes: set[str] = set()
    codes.update(
        str(c).strip().lower()
        for c in Feed.objects.values_list("language", flat=True).distinct()
        if c
    )
    codes.update(
        str(c).strip().lower()
        for c in UserContentLanguage.objects.values_list("language", flat=True).distinct()
        if c
    )
    codes.add("en")
    for code in sorted(codes):
        Language.objects.get_or_create(
            code=code,
            defaults={
                "name": code.upper(),
                "sort_order": 100,
                "created_at": now,
                "updated_at": now,
            },
        )
    # Normalize blank feed languages to und before FK.
    Feed.objects.filter(language="").update(language="und")
    Language.objects.get_or_create(
        code="und",
        defaults={
            "name": "Unknown",
            "sort_order": 90,
            "created_at": now,
            "updated_at": now,
        },
    )


def backfill_en_localizations(apps, schema_editor) -> None:
    StoryThread = apps.get_model("news", "StoryThread")
    StoryThreadLocalization = apps.get_model("news", "StoryThreadLocalization")
    Language = apps.get_model("news", "Language")
    now = django.utils.timezone.now()
    en = Language.objects.filter(code="en").first()
    if en is None:
        return
    rows: list[object] = []
    for thread in StoryThread.objects.all().iterator():
        label = (thread.label or "").strip()
        summary = (thread.summary or "").strip()
        if not label and not summary:
            continue
        rows.append(
            StoryThreadLocalization(
                story_thread_id=thread.id,
                language_id=en.code,
                label=label[:300],
                summary=summary,
                created_at=now,
                updated_at=now,
            )
        )
        if len(rows) >= 500:
            StoryThreadLocalization.objects.bulk_create(rows, ignore_conflicts=True)
            rows = []
    if rows:
        StoryThreadLocalization.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0019_story_thread_summary_and_brief_item_polymorphic"),
    ]

    operations = [
        migrations.CreateModel(
            name="Language",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                ("code", models.CharField(max_length=8, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.RunPython(seed_languages, migrations.RunPython.noop),
        migrations.RunPython(ensure_language_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="feed",
            name="language",
            field=models.ForeignKey(
                db_column="language",
                default="en",
                help_text="ISO 639-1 content language (e.g. en, fr, de). Use und when unknown.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="feeds",
                to="news.language",
                to_field="code",
            ),
        ),
        migrations.AlterField(
            model_name="usercontentlanguage",
            name="language",
            field=models.ForeignKey(
                db_column="language",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_preferences",
                to="news.language",
                to_field="code",
            ),
        ),
        migrations.CreateModel(
            name="StoryThreadLocalization",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(blank=True, max_length=300)),
                ("summary", models.TextField(blank=True)),
                (
                    "language",
                    models.ForeignKey(
                        db_column="language",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="thread_localizations",
                        to="news.language",
                        to_field="code",
                    ),
                ),
                (
                    "story_thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="localizations",
                        to="news.storythread",
                    ),
                ),
            ],
            options={
                "ordering": ["language_id", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="storythreadlocalization",
            constraint=models.UniqueConstraint(
                fields=("story_thread", "language"),
                name="uniq_storythreadlocalization_thread_lang",
            ),
        ),
        migrations.AlterField(
            model_name="storythread",
            name="label",
            field=models.CharField(
                blank=True,
                help_text="English mirror of the en localization (bootstrap + summarizer).",
                max_length=300,
            ),
        ),
        migrations.AlterField(
            model_name="storythread",
            name="summary",
            field=models.TextField(
                blank=True,
                help_text="English mirror of the en localization AI digest.",
            ),
        ),
        migrations.AlterField(
            model_name="storythread",
            name="summarized_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When localizations were last generated (6h throttle on refresh).",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_en_localizations, migrations.RunPython.noop),
    ]
