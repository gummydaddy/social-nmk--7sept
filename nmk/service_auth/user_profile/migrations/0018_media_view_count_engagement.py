# Generated by Django 4.2.10 on 2024-07-05 11:17

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("user_profile", "0017_delete_comment"),
    ]

    operations = [
        migrations.AddField(
            model_name="media",
            name="view_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="Engagement",
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
                ("engagement_type", models.CharField(max_length=50)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "media",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="user_profile.media",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
