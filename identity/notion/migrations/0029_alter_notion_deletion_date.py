# Generated by Django 4.2.10 on 2024-07-20 08:50

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0028_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 19, 8, 50, 48, 844415, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
