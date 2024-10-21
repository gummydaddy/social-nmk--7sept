# Generated by Django 4.2.10 on 2024-05-28 06:49

from django.db import migrations, models
import service_auth.user_profile.storage


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0007_delete_follow"),
    ]

    operations = [
        migrations.CreateModel(
            name="Hashtag",
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
                ("name", models.CharField(max_length=100, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name="media",
            name="media_type",
            field=models.CharField(
                choices=[("image", "Image"), ("video", "Video")],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="media",
            name="file",
            field=models.FileField(
                storage=service_auth.user_profile.storage.CompressedMediaStorage(),
                upload_to="media_uploads/",
            ),
        ),
        migrations.AddField(
            model_name="media",
            name="hashtags",
            field=models.ManyToManyField(
                blank=True, related_name="media", to="user_profile.hashtag"
            ),
        ),
    ]
