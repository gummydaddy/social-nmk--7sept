# Generated by Django 4.2.10 on 2024-07-01 10:55

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0016_delete_ad"),
    ]

    operations = [
        migrations.DeleteModel(name="Comment",),
    ]
