# your_project/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'socyfie_application.settings')

app = Celery(
    'socyfie_application',
    broker='redis://:090399Akash%24@15.235.192.133:6379/0',  
    backend='redis://:090399Akash%24@15.235.192.133:6379/0'
)

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
        'schedule': crontab(minute='49'),
    },
    'delete-expired-stories-every-hour': {
        'task': 'service_auth.user_profile.tasks.delete_expired_stories',
        'schedule': crontab(minute='25'),  # Runs hourly
    },
    'delete-old-notifications-every-day': {
        'task': 'service_auth.notion.tasks.delete_old_notifications',
        'schedule': crontab(minute='0', hour='*/7'),  # Runs daily at midnight
    },
    'update-trending-every-20-mins': {
        'task': 'service_auth.user_profile.tasks.update_trending_scores',
        'schedule': crontab(minute='*/19'),
    },
    'remove-private-media-from-trending': {
        'task': 'service_auth.user_profile.tasks.remove_private_media_from_trending',
        #'schedule': crontab(minute=0, hour='*/1'),  # Every hour
        'schedule': crontab(minute='*/7'),  # Every hour

    },
    "dispatch-user-recommendations-every-20-min": {
        "task": "service_auth.user_profile.tasks.dispatch_recommendation_tasks",
        "schedule": crontab(minute="*/5"),
    },

    'sync-not-interested': {
        'task': 'service_auth.user_profile.tasks.sync_not_interested_to_redis',
        'schedule': crontab(minute='*/23'),  # Every hour
        #"schedule": crontab(minute="*/2"),
    },
    'populate-creator-mappings': {
        'task': 'service_auth.user_profile.tasks.populate_creator_mappings',
        'schedule': crontab(minute=0, hour=4),  # Daily at 2 AM
        #"schedule": crontab(minute="*/2"),
    },
    'cleanup-redis-data': {
        'task': 'service_auth.user_profile.tasks.cleanup_stale_redis_data',
        'schedule': crontab(minute=0, hour=2),  # Daily at 2 AM
        #"schedule": crontab(minute="*/2"),
    },
    'rebuild-penalties': {
        'task': 'service_auth.user_profile.tasks.rebuild_penalties_from_not_interested',
        'schedule': crontab(minute=0, hour=3),  # Daily at 3 AM
        #"schedule": crontab(minute="*/8"),
    },


}

'''
app.conf.task_routes = {
    'service_auth.user_profile.tasks.process_media_upload': {
        'queue': 'media_worker',
    },
}
'''
