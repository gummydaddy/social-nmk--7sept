# Generated by Django 4.2.10 on 2024-05-23 07:24

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Block",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("number", models.IntegerField()),
                ("hash", models.CharField(max_length=100)),
                ("previous", models.CharField(max_length=100)),
                ("data", models.TextField()),
                ("nonce", models.IntegerField()),
            ],
        ),
    ]
