# Generated by Django 4.2.10 on 2024-09-03 09:22

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0072_alter_notion_deletion_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 10, 3, 9, 22, 16, 336866, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
