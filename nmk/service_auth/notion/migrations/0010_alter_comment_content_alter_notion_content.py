# Generated by Django 4.2.10 on 2024-05-27 10:32

from django.db import migrations
import service_auth.notion.fields


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0009_remove_notion_custom_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="comment",
            name="content",
            field=service_auth.notion.fields.CompressedTextField(),
        ),
        migrations.AlterField(
            model_name="notion",
            name="content",
            field=service_auth.notion.fields.CompressedTextField(),
        ),
    ]
