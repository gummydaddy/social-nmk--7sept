from celery import shared_task
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import UserUpload
from service_auth.only_card.utils import is_storage_full

@shared_task
def process_file_upload(upload_id):
    try:
        upload = UserUpload.objects.get(id=upload_id)

        # Simulate storage check logic (adjust according to your business logic)
        user = upload.user
        if is_storage_full(user):  # You'll need to implement this
            upload.delete()  # Optionally roll back saved object
            # Log or notify user/admin
            return "Storage full"

        # If storage is fine, proceed (nothing to do since it's already saved)
        return "Upload successful"
    except UserUpload.DoesNotExist:
        return "Upload object not found"
    except Exception as e:
        return f"Error: {str(e)}"

