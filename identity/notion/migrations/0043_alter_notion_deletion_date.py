# Generated by Django 4.2.10 on 2024-08-02 13:58

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0042_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 9, 1, 13, 58, 33, 614971, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
