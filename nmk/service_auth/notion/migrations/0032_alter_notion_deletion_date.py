# Generated by Django 4.2.10 on 2024-07-20 09:09

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0031_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 19, 9, 9, 13, 240064, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
