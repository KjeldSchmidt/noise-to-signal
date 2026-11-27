# Generated manually for account-delete safety.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0022_user_onboarding"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="feed",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional first-adder metadata for custom feeds.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="custom_feeds",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
