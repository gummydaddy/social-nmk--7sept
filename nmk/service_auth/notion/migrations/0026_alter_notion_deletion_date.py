# Generated by Django 4.2.10 on 2024-07-20 07:14

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0025_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 19, 7, 14, 8, 300620, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
