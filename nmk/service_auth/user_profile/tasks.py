# service_auth/user_profile/tasks.py

from django.utils import timezone
from datetime import timedelta
from celery import shared_task
from django.utils.timezone import now
from service_auth.user_profile.models import Story

@shared_task
def delete_expired_stories():
    expired_stories = Story.objects.filter(created_at__lt=now() - timezone.timedelta(hours=24))
    count = expired_stories.count()
    for story in expired_stories:
        if story.media:
            story.media.delete_file()  # Optional: Delete the associated file
        story.delete()
    return f"Deleted {count} expired stories."
