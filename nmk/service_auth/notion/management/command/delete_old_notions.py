# # notion/tasks.py
# from celery import shared_task
# from django.utils import timezone
# from notion.models import Notion

# @shared_task
# def delete_old_notions():
#     now = timezone.now()
#     old_notions = Notion.objects.filter(deletion_date__lt=now)
#     count = old_notions.count()
#     old_notions.delete()
#     return f'{count} old notions deleted.'

from celery import shared_task
from django.utils import timezone
from notion.models import Notion
import logging

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def delete_old_notions():
    now = timezone.now()
    try:
        old_notions = Notion.objects.filter(deletion_date__lt=now)
        count = old_notions.count()
        logging.info(f"Get the count : {count} and old_notions: {old_notions}")
        old_notions.delete()
        logging.info(f'{count} old notions deleted.')
        return f'{count} old notions deleted.'
    except Exception as e:
        logging.error(f"Error deleting old notions: {e}")
        return f"Error: {e}"
