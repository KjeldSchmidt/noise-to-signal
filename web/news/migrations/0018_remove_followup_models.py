from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0017_user_theme_affinity"),
    ]

    operations = [
        migrations.DeleteModel(name="FollowUpAnswer"),
        migrations.DeleteModel(name="FollowUpQuestion"),
    ]
