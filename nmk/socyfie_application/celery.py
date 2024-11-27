# your_project/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'socyfie_application.settings')

app = Celery('socyfie_application')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# Namespace='CELERY' means all celery-related configuration keys
# should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Define the beat schedule
app.conf.beat_schedule =  {
    'delete-old-notions-every-day': {
        'task': 'service_auth.notion.tasks.delete_old_notions',
        'schedule': crontab(minute='*'),
    },
    'delete-expired-stories-every-hour': {
        'task': 'service_auth.user_profile.tasks.delete_expired_stories',
        'schedule': crontab(minute='*'),  # Runs hourly
    },
    'delete-old-notifications-every-day': {
        'task': 'service_auth.notion.tasks.delete_old_notifications',
        'schedule': crontab(minute='*'),  # Runs daily at midnight
    },
}