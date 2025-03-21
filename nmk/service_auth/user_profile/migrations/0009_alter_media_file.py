# Generated by Django 4.2.10 on 2024-05-28 06:51

from django.db import migrations, models
import service_auth.user_profile.storage


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0008_hashtag_media_media_type_alter_media_file_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="media",
            name="file",
            field=models.FileField(
                storage=service_auth.user_profile.storage.CompressedMediaStorage(),
                upload_to="media/",
            ),
        ),
    ]
