# tasks.py
from celery import shared_task
from django.utils.timezone import now
from .models import Notion
import logging

logger = logging.getLogger(__name__)

@shared_task
def delete_old_notions():
    logger.info("Running task to delete old notions...")
    current_time = now()
    # Filter notions based on the deletion_date and delete them
    old_notions = Notion.objects.filter(deletion_date__lt=current_time).delete()
    # old_notions.delete()  # This should no longer raise errors if migrations are properly handled
    # deleted_count, _ = old_notions.delete()  # Returns a tuple of (number of deletions, dict of deletions)
    logger.info(f"Deleted {old_notions} old notions.")
