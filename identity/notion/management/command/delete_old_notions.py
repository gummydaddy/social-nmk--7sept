# your_app/management/commands/delete_old_notions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from your_app.models import Notion

class Command(BaseCommand):
    help = 'Deletes notions older than their scheduled deletion date'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        old_notions = Notion.objects.filter(deletion_date__lt=now)
        count = old_notions.count()
        old_notions.delete()
        self.stdout.write(f'{count} notions deleted.')
