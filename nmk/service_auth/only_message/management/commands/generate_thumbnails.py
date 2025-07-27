import os
from django.core.management.base import BaseCommand
from service_auth.user_profile.models import Media

class Command(BaseCommand):
    help = 'Generates thumbnails for media that are images and missing thumbnails.'

    def handle(self, *args, **kwargs):
        total = 0
        generated = 0
        skipped = 0

        queryset = Media.objects.filter(file__isnull=False)

        for media in queryset:
            total += 1

            # Skip if thumbnail already exists
            if media.thumbnail and media.thumbnail.name:
                skipped += 1
                self.stdout.write(f"Skipped (already has thumbnail): {media.file.name}")
                continue

            try:
                media.generate_thumbnail()
                media.save(update_fields=["thumbnail"])
                generated += 1
                self.stdout.write(f"Generated thumbnail for: {media.file.name}")
            except Exception as e:
                self.stderr.write(f"Failed to generate thumbnail for {media.file.name}: {e}")

        self.stdout.write(f"\nSummary:")
        self.stdout.write(f"Total media checked: {total}")
        self.stdout.write(f"Thumbnails generated: {generated}")
        self.stdout.write(f"Skipped (existing thumbnails): {skipped}")
