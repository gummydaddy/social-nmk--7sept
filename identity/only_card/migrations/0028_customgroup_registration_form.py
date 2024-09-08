# Generated by Django 4.2.10 on 2024-05-07 13:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("only_card", "0027_registrationform_association_name_userassociation"),
    ]

    operations = [
        migrations.AddField(
            model_name="customgroup",
            name="registration_form",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="only_card.registrationform",
            ),
        ),
    ]
