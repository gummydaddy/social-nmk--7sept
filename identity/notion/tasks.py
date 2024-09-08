# your_app/tasks.py
from celery import shared_task
from django.utils import timezone
from notion.models import Notion

@shared_task
def delete_old_notions():
    now = timezone.now()
    Notion.objects.filter(deletion_date__lt=now).delete()
