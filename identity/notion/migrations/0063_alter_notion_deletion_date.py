# Generated by Django 4.2.10 on 2024-08-25 05:17

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0062_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 9, 24, 5, 17, 38, 934376, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
