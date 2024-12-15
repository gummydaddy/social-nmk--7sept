# service_auth/user_profile/tasks.py

from django.utils import timezone
from datetime import timedelta
from celery import shared_task
from django.utils.timezone import now
from django.db import transaction
from sklearn import logger
from service_auth.user_profile.models import Story

# @shared_task
# def delete_expired_stories():
#     expired_stories = Story.objects.filter(created_at__lt=now() - timezone.timedelta(hours=24))
#     count = expired_stories.count()
#     for story in expired_stories:
#         # if story.media:
#         if story.media and story.media.file:  # Check if media has a file
#             # story.media.delete_file()  # Optional: Delete the associated file
#             story.media.file.delete(save=True)  # Delete the media file from storage
#         story.delete()
#     return f"Deleted {count} expired stories."


@shared_task
def delete_expired_stories():
    expired_stories = Story.objects.filter(created_at__lt=now() - timezone.timedelta(hours=24))
    count = expired_stories.count()

    # Use a transaction to ensure consistency
    with transaction.atomic():
        for story in expired_stories:
            # Delete associated media instance if it exists
            if story.media:
                try:
                    # Delete the media file from storage
                    story.media.file.delete(save=False)
                    
                    # Delete the media instance
                    story.media.delete()
                except Exception as e:
                    logger.error(f"Error deleting media for story {story.id}: {e}")

            # Delete the story instance
            story.delete()

    return f"Deleted {count} expired stories and their associated media."