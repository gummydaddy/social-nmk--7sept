# Generated by Django 4.2.10 on 2024-05-13 17:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0036_remove_notion_user_notion_created_by_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion", name="content", field=models.TextField(null=True),
        ),
    ]
