# Generated by Django 4.2.10 on 2024-07-29 16:02

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0039_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 28, 16, 2, 27, 356321, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
