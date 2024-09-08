# Generated by Django 4.2.10 on 2024-05-13 17:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("only_card", "0035_remove_notion_comments_remove_notion_likes"),
    ]

    operations = [
        migrations.RemoveField(model_name="notion", name="user",),
        migrations.AddField(
            model_name="notion",
            name="created_by",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="notion",
            name="content",
            field=models.TextField(blank=True, null=True),
        ),
    ]
