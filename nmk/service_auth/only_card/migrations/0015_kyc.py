# Generated by Django 4.2.10 on 2024-04-24 16:38

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("only_card", "0014_rename_user_id_card_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="KYC",
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
                (
                    "kyc_video",
                    models.FileField(blank=True, null=True, upload_to="kyc_videos/"),
                ),
                ("phone_number", models.CharField(max_length=15)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
