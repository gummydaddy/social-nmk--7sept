# Generated by Django 4.2.10 on 2024-08-03 11:55

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0043_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 9, 2, 11, 55, 44, 511793, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
