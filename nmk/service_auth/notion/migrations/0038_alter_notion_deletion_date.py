# Generated by Django 4.2.10 on 2024-07-25 09:43

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0037_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 24, 9, 43, 48, 762053, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
