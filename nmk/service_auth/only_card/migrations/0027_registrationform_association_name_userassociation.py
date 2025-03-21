# Generated by Django 4.2.10 on 2024-05-07 13:21

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("only_card", "0026_customgroup_legal_documents_association"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrationform",
            name="association_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.CreateModel(
            name="UserAssociation",
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
                ("association_name", models.CharField(max_length=100)),
                ("association_email", models.EmailField(max_length=254)),
                ("is_approved", models.BooleanField(default=False)),
                (
                    "subgroup",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="only_card.customgroup",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
