# Generated by Django 4.2.10 on 2024-04-20 22:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0009_rename_serviceproviderregistration_registration_form"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registration_form",
            name="legal_documents",
            field=models.FileField(default="degree", upload_to="legal_documents/"),
        ),
    ]
