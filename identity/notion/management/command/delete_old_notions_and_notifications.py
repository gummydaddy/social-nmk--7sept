# your_app/management/commands/delete_old_notions_and_notifications.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from notion.models import Notion, Notification

class Command(BaseCommand):
    help = 'Deletes notions older than their scheduled deletion date and notifications older than 8 days'

    def handle(self, *args, **kwargs):
        now = timezone.now()

        # Delete old notions based on deletion_date
        old_notions = Notion.objects.filter(deletion_date__lt=now)
        notions_count = old_notions.count()
        old_notions.delete()

        # Delete notifications older than 8 days
        eight_days_ago = now - timedelta(days=8)
        old_notifications = Notification.objects.filter(created_at__lt=eight_days_ago)
        notifications_count = old_notifications.count()
        old_notifications.delete()

        self.stdout.write(f'{notions_count} notions and {notifications_count} notifications deleted.')
