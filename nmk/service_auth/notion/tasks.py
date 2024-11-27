# tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.utils.timezone import now
from .models import Notion, Notification
import logging

logger = logging.getLogger(__name__)

@shared_task
def delete_old_notions():
    logger.info("Running task to delete old notions...")
    current_time = now()
    # Filter notions based on the deletion_date and delete them
    old_notions = Notion.objects.filter(deletion_date__lt=current_time).delete()
    logger.info(f"Deleted {old_notions} old notions.")

@shared_task
def delete_old_notifications():
    eight_days_ago = now() - timezone.timedelta(days=8)
    old_notifications = Notification.objects.filter(created_at__lt=eight_days_ago)
    count = old_notifications.count()
    old_notifications.delete()
    return f"Deleted {count} old notifications."