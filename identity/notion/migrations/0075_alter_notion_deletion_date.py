# Generated by Django 4.2.10 on 2024-09-09 10:45

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0074_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 10, 9, 10, 45, 55, 494967, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
