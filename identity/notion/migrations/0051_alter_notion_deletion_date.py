# Generated by Django 4.2.10 on 2024-08-11 15:55

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0050_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 9, 10, 15, 55, 20, 437754, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
