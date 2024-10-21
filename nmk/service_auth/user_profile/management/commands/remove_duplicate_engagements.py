# user_profile/management/commands/remove_duplicate_engagements.py
from django.core.management.base import BaseCommand
from user_profile.models import Engagement
from django.db.models import Count

class Command(BaseCommand):
    help = 'Remove duplicate engagements'

    def handle(self, *args, **options):
        duplicates = (
            Engagement.objects.values('media', 'user', 'engagement_type')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        for duplicate in duplicates:
            engagements = Engagement.objects.filter(
                media=duplicate['media'],
                user=duplicate['user'],
                engagement_type=duplicate['engagement_type']
            )
            # Keep only the first engagement and delete the rest
            engagements.exclude(id=engagements.first().id).delete()

        self.stdout.write(self.style.SUCCESS('Successfully removed duplicate engagements'))
