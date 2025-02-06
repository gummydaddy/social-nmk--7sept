# Generated by Django 4.2.10 on 2024-04-24 15:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("only_card", "0012_alter_registrationform_legal_documents"),
    ]

    operations = [
        migrations.RemoveField(model_name="card", name="description",),
        migrations.RemoveField(model_name="card", name="image",),
        migrations.RemoveField(model_name="card", name="name",),
        migrations.RemoveField(model_name="card", name="uploaded_at",),
        migrations.AddField(
            model_name="card",
            name="card_image",
            field=models.ImageField(blank=True, null=True, upload_to="card_images/"),
        ),
        migrations.AddField(
            model_name="card",
            name="card_number",
            field=models.CharField(
                default="NMK 0000000000000000", max_length=30, unique=True
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="card",
            name="card_type",
            field=models.CharField(default="only_id", max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="card",
            name="user_id",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
