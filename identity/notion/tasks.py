# # your_app/tasks.py
# import logging
# from celery import shared_task
# from django.utils import timezone
# from datetime import timedelta
# from notion.models import Notion, Notification
# from django.contrib.auth.models import User as AuthUser

# logger = logging.getLogger(__name__)

# @shared_task
# def delete_old_notions_and_notifications():
#     try:
#         now = timezone.now()
#         old_notions = Notion.objects.filter(deletion_date__lt=now)
#         notions_count = old_notions.count()
#         old_notions.delete()

#         eight_days_ago = now - timedelta(days=8)
#         old_notifications = Notification.objects.filter(created_at__lt=eight_days_ago)
#         notifications_count = old_notifications.count()
#         old_notifications.delete()

#         logger.info(f'{notions_count} notions and {notifications_count} notifications deleted.')
#         return f'{notions_count} notions and {notifications_count} notifications deleted.'
#     except Exception as e:
#         logger.error(f'Error deleting old notions and notifications: {e}')
#         raise


# @shared_task
# def send_tagged_user_notifications(notion_id, tagged_usernames, sender_username):
#     try:
#         for username in tagged_usernames:
#             try:
#                 tagged_user = AuthUser.objects.get(username=username)
#                 Notification.objects.create(
#                     user=tagged_user,
#                     content=f'You were tagged in a notion by {sender_username}'
#                 )
#                 logger.info(f'Notification sent to {username}')
#             except AuthUser.DoesNotExist:
#                 logger.warning(f'User {username} does not exist')
#     except Exception as e:
#         logger.error(f'Error sending notifications: {e}')
#         raise

# your_app/tasks.py
# from celery import shared_task
# from django.utils import timezone
# from notion.models import Notion

# @shared_task
# def delete_old_notions():
#     now = timezone.now()
#     Notion.objects.filter(deletion_date__lt=now).delete()


# tasks.py
from celery import shared_task
from django.utils.timezone import now
from .models import Notion

@shared_task
def delete_old_notions():
    current_time = now()
    # Filter notions based on the deletion_date and delete them
    old_notions = Notion.objects.filter(deletion_date__lt=current_time)
    old_notions.delete()  # This should no longer raise errors if migrations are properly handled

