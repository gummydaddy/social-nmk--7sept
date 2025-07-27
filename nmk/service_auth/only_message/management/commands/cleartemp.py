import os
import time
import logging
from pathlib import Path
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Delete temporary upload files older than a given age (default 12 hours)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            default='/tmp',
            help='Directory to search for temp files'
        )
        parser.add_argument(
            '--ext',
            type=str,
            default='.upload',
            help='File extension to match (default: .upload)'
        )
        parser.add_argument(
            '--max-age',
            type=int,
            default=43200,  # 12 hours in seconds
            help='Max age (in seconds) of files to keep'
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        ext = options['ext']
        max_age = options['max_age']
        now = time.time()
        removed_count = 0

        if not path.exists():
            self.stdout.write(self.style.WARNING(f"Path {path} does not exist."))
            return

        self.stdout.write(f"Scanning {path} for *{ext} files older than {max_age} seconds...")

        for file in path.glob(f'*{ext}'):
            try:
                file_mtime = file.stat().st_mtime
                if now - file_mtime > max_age:
                    file.unlink()
                    removed_count += 1
                    logger.info(f"Deleted temp file: {file}")
            except Exception as e:
                logger.error(f"Error deleting {file}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Deleted {removed_count} expired temp files."))
