# Generated by Django 4.2.10 on 2024-05-06 13:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0025_customgroup_admins"),
    ]

    operations = [
        migrations.AddField(
            model_name="customgroup",
            name="legal_documents_Association",
            field=models.FileField(
                blank=True, null=True, upload_to="legal_documents_Association/"
            ),
        ),
    ]
