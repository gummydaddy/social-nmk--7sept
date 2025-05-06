import os
from django.conf import settings
from service_auth.only_card.models import UserUpload  # adjust if you use a different model

MAX_STORAGE_MB = 500  # You can change this limit per user or make it dynamic

def is_storage_full(user):
    uploads = UserUpload.objects.filter(user=user)

    total_size_bytes = sum(upload.file.size for upload in uploads if upload.file)
    total_size_mb = total_size_bytes / (1024 * 1024)

    return total_size_mb > MAX_STORAGE_MB
