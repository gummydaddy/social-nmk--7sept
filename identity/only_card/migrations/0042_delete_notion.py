# Generated by Django 4.2.10 on 2024-05-20 18:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0041_alter_notion_user"),
    ]

    operations = [
        migrations.DeleteModel(name="Notion",),
    ]
