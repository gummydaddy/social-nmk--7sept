# Generated by Django 4.2.10 on 2024-07-04 18:27

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notion", "0020_alter_follow_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="notion",
            name="deletion_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2024, 8, 3, 18, 27, 29, 41274, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]
