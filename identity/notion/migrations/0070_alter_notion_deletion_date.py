# Generated by Django 4.2.10 on 2024-08-31 15:46

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0069_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 9, 30, 15, 46, 38, 568202, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
