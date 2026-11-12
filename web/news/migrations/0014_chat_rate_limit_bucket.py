import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("news", "0013_feed_http_poll_validators"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatRateLimitBucket",
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
                ("bucket_key", models.CharField(db_index=True, max_length=32)),
                ("window_start", models.DateTimeField()),
                ("count", models.PositiveIntegerField(default=0)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_rate_limit_buckets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="chatratelimitbucket",
            constraint=models.UniqueConstraint(
                fields=("user", "bucket_key", "window_start"),
                name="uniq_chat_rate_limit_bucket",
            ),
        ),
        migrations.AddIndex(
            model_name="chatratelimitbucket",
            index=models.Index(fields=["window_start"], name="chat_rl_window_idx"),
        ),
    ]
