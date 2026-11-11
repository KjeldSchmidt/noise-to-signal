# Expanded curated theme catalog + ThemeSuggestion counters

from django.db import migrations, models
import django.utils.timezone


CURATED_THEMES = [
    ("politics", "Politics", 10),
    ("elections", "Elections", 20),
    ("conflict", "Conflict", 30),
    ("geopolitics", "Geopolitics", 40),
    ("economy", "Economy", 50),
    ("markets", "Markets", 60),
    ("business", "Business", 70),
    ("tech", "Technology", 80),
    ("science", "Science", 90),
    ("climate", "Climate", 100),
    ("energy", "Energy", 110),
    ("environment", "Environment", 120),
    ("health", "Health", 130),
    ("education", "Education", 140),
    ("justice", "Justice", 150),
    ("immigration", "Immigration", 160),
    ("labor", "Labor", 170),
    ("sports", "Sports", 180),
    ("culture", "Culture", 190),
    ("media", "Media", 200),
    ("disaster", "Disaster", 210),
]


def seed_curated_themes(apps, schema_editor):
    Theme = apps.get_model("news", "Theme")
    for slug, label, order in CURATED_THEMES:
        Theme.objects.update_or_create(
            slug=slug,
            defaults={"label": label, "sort_order": order, "is_active": True},
        )
    Theme.objects.filter(slug="policy").update(is_active=False)


def unseed_curated_themes(apps, schema_editor):
    Theme = apps.get_model("news", "Theme")
    new_slugs = {
        "politics",
        "geopolitics",
        "economy",
        "business",
        "environment",
        "education",
        "justice",
        "immigration",
        "labor",
        "media",
    }
    Theme.objects.filter(slug__in=new_slugs).delete()
    Theme.objects.filter(slug="policy").update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0006_article_story_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="ThemeSuggestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("raw", models.SlugField(max_length=64, unique=True)),
                ("count", models.PositiveIntegerField(default=0)),
                (
                    "last_seen_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("last_example_title", models.CharField(blank=True, max_length=300)),
            ],
            options={
                "ordering": ["-count", "raw"],
            },
        ),
        migrations.RunPython(seed_curated_themes, unseed_curated_themes),
    ]
