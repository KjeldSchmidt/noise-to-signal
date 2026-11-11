# Generated manually for pgvector embeddings + story threads

import django.db.models.deletion
from django.db import migrations, models
from pgvector.django import VectorExtension, VectorField


def create_vector_extension(apps, schema_editor):
    """Postgres only — SQLite test DBs skip the extension."""
    if schema_editor.connection.vendor != "postgresql":
        return
    VectorExtension().database_forwards("news", schema_editor, None, None)


def drop_vector_extension(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    VectorExtension().database_backwards("news", schema_editor, None, None)


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0003_article_image_url"),
    ]

    operations = [
        migrations.RunPython(create_vector_extension, drop_vector_extension),
        migrations.CreateModel(
            name="StoryThread",
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
                ("label", models.CharField(blank=True, max_length=300)),
                (
                    "centroid",
                    VectorField(blank=True, dimensions=1024, null=True),
                ),
                ("last_published_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-last_published_at"],
            },
        ),
        migrations.AddField(
            model_name="article",
            name="embedding",
            field=VectorField(blank=True, dimensions=1024, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="embedding_model",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="article",
            name="embedded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="near_duplicate_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="near_duplicates",
                to="news.article",
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="story_thread",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="articles",
                to="news.storythread",
            ),
        ),
    ]
