from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0008_timestamped_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="enrichment_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ok", "OK"),
                    ("degraded", "Degraded"),
                ],
                db_index=True,
                default="",
                help_text="ok = extract succeeded; degraded = extract ok but geocode failed.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="extract_model",
            field=models.CharField(
                blank=True,
                help_text="Bedrock/LangChain model id used for place/theme extract.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="enriched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
