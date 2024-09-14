# celery.py

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nmk.settings')

app = Celery('nmk')

# Use the configuration from Django settings, using the `CELERY_` prefix for all Celery-related keys.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Ensure broker connection retry on startup (this is already set in settings.py)
# CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True is already set via settings


# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Define the beat schedule for periodic tasks

app.conf.beat_schedule = {
    'delete-old-notions-every-day': {
        'task': 'notion.tasks.delete_old_notions',
        'schedule': crontab(hour=0, minute=0),
    },
}
# app.conf.beat_schedule = {
#     # Task to run every 5 minutes
#     # 'every-5-minutes': {
#     #     'task': 'nmk.tasks.update',   # Ensure that this task exists in 'nmk/tasks.py'
#     #     'schedule': crontab(minute='*/5'),  # Runs every 5 minutes
#     # },

#     # Task to delete old notions and notifications daily at midnight
#     'delete-old-notions-and-notifications-every-day': {
#         'task': 'your_app.tasks.delete_old_notions_and_notifications',
#         'schedule': crontab(hour=0, minute=0),  # Runs daily at midnight
#     },
# }
