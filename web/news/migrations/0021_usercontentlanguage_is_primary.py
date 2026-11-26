# Add is_primary on UserContentLanguage + backfill one primary per user.

from __future__ import annotations

from django.db import migrations, models


def backfill_primary(apps, schema_editor) -> None:
    UserContentLanguage = apps.get_model("news", "UserContentLanguage")
    user_ids = (
        UserContentLanguage.objects.order_by("user_id").values_list("user_id", flat=True).distinct()
    )
    for user_id in user_ids:
        rows = list(UserContentLanguage.objects.filter(user_id=user_id).order_by("language_id"))
        if not rows:
            continue
        if any(row.is_primary for row in rows):
            continue
        en = next((row for row in rows if row.language_id == "en"), None)
        chosen = en or rows[0]
        UserContentLanguage.objects.filter(pk=chosen.pk).update(is_primary=True)


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0020_language_and_thread_localizations"),
    ]

    operations = [
        migrations.AddField(
            model_name="usercontentlanguage",
            name="is_primary",
            field=models.BooleanField(
                default=False,
                help_text="Primary language for UI chrome and story title/summary selection.",
            ),
        ),
        migrations.RunPython(backfill_primary, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="usercontentlanguage",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_primary=True),
                fields=("user",),
                name="uniq_user_primary_content_language",
            ),
        ),
    ]
