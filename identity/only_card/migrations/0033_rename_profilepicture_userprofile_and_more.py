# Generated by Django 4.2.10 on 2024-05-13 07:31

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("only_card", "0032_rename_profile_picture_profilepicture_image"),
    ]

    operations = [
        migrations.RenameModel(old_name="ProfilePicture", new_name="UserProfile",),
        migrations.RenameField(
            model_name="userprofile", old_name="image", new_name="profile_picture",
        ),
    ]
