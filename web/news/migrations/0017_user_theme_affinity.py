import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("news", "0016_user_brief"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserThemeAffinity",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("more_count", models.PositiveIntegerField(default=0)),
                ("less_count", models.PositiveIntegerField(default=0)),
                (
                    "theme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_affinities",
                        to="news.theme",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="theme_affinities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["theme__sort_order", "theme__slug"],
            },
        ),
        migrations.AddConstraint(
            model_name="userthemeaffinity",
            constraint=models.UniqueConstraint(
                fields=("user", "theme"),
                name="uniq_userthemeaffinity_user_theme",
            ),
        ),
    ]
