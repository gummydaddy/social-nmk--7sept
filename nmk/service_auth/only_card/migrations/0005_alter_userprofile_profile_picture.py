# Generated by Django 4.2.10 on 2024-04-16 10:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0004_userprofile_profile_picture"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="profile_picture",
            field=models.ImageField(
                blank=True, null=True, upload_to="profile_picture/"
            ),
        ),
    ]
