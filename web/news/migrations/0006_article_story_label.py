from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0005_article_place_themes"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="story_label",
            field=models.CharField(
                blank=True,
                help_text="Short generic event name from extract (e.g. Spanish Rail Crash).",
                max_length=120,
            ),
        ),
    ]
