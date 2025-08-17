# signals.py

from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import UserUpload

@receiver(post_delete, sender=UserUpload)
def delete_user_upload_file_on_delete(sender, instance, **kwargs):
    # Delete main file from bucket
    if instance.file:
        try:
            instance.file.delete(save=False)
            print("Deleted uploaded file from bucket")
        except Exception as e:
            print(f"Error deleting uploaded file: {e}")

    # Optional: Delete any thumbnails or other related files if you store them separately
    if hasattr(instance, 'thumbnail') and instance.thumbnail:
        try:
            instance.thumbnail.delete(save=False)
            print("Deleted thumbnail from bucket")
        except Exception as e:
            print(f"Error deleting thumbnail: {e}")
