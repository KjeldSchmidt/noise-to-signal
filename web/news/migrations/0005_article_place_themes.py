# Theme catalog + hierarchical place fields for articles and LOIs

from django.db import migrations, models

SEED_THEMES = [
    ("climate", "Climate", 10),
    ("energy", "Energy", 20),
    ("markets", "Markets", 30),
    ("elections", "Elections", 40),
    ("conflict", "Conflict", 50),
    ("health", "Health", 60),
    ("tech", "Technology", 70),
    ("science", "Science", 80),
    ("sports", "Sports", 90),
    ("culture", "Culture", 100),
    ("policy", "Policy", 110),
    ("disaster", "Disaster", 120),
]


def seed_themes(apps, schema_editor):
    Theme = apps.get_model("news", "Theme")
    for slug, label, order in SEED_THEMES:
        Theme.objects.update_or_create(
            slug=slug,
            defaults={"label": label, "sort_order": order, "is_active": True},
        )


def unseed_themes(apps, schema_editor):
    Theme = apps.get_model("news", "Theme")
    Theme.objects.filter(slug__in=[s for s, _, _ in SEED_THEMES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0004_article_embedding_storythread"),
    ]

    operations = [
        migrations.CreateModel(
            name="Theme",
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
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("label", models.CharField(max_length=120)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["sort_order", "slug"],
            },
        ),
        migrations.AddField(
            model_name="locationofinterest",
            name="admin1",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="locationofinterest",
            name="country_code",
            field=models.CharField(blank=True, db_index=True, max_length=2),
        ),
        migrations.AddField(
            model_name="locationofinterest",
            name="geo_level",
            field=models.CharField(
                blank=True,
                choices=[
                    ("global", "Global"),
                    ("country", "Country"),
                    ("admin1", "Region / state"),
                    ("locality", "City / locality"),
                ],
                default="locality",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="locationofinterest",
            name="locality",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="article",
            name="admin1",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="article",
            name="country_code",
            field=models.CharField(blank=True, db_index=True, max_length=2),
        ),
        migrations.AddField(
            model_name="article",
            name="geo_confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="geo_level",
            field=models.CharField(
                choices=[
                    ("global", "Global"),
                    ("country", "Country"),
                    ("admin1", "Region / state"),
                    ("locality", "City / locality"),
                ],
                db_index=True,
                default="global",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="locality",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="article",
            name="longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="place_label",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="article",
            name="themes",
            field=models.ManyToManyField(blank=True, related_name="articles", to="news.theme"),
        ),
        migrations.RunPython(seed_themes, unseed_themes),
    ]
