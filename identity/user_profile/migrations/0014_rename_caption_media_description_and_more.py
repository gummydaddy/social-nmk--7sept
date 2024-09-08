# Generated by Django 4.2.10 on 2024-06-06 18:28

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0013_remove_media_description"),
    ]

    operations = [
        migrations.RenameField(
            model_name="media", old_name="caption", new_name="description",
        ),
        migrations.RemoveField(model_name="media", name="tagged_users",),
    ]
