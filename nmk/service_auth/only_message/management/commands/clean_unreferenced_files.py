"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from service_auth.user_profile.models import Profile, Media

class Command(BaseCommand):
    help = 'Deletes unreferenced media files from profile_picture, cover_photo, and media.file'

    def handle(self, *args, **kwargs):
        media_root = settings.MEDIA_ROOT

        # 1. Get all referenced files
        referenced_files = set()

        for profile in Profile.objects.all():
            if profile.profile_picture:
                referenced_files.add(os.path.abspath(profile.profile_picture.path))
            if profile.cover_photo:
                referenced_files.add(os.path.abspath(profile.cover_photo.path))

        for media in Media.objects.all():
            if media.file:
                referenced_files.add(os.path.abspath(media.file.path))

        # 2. Walk through the media root and check all files
        deleted_files = []
        for root, dirs, files in os.walk(media_root):
            for file in files:
                file_path = os.path.abspath(os.path.join(root, file))
                if file_path not in referenced_files:
                    try:
                        os.remove(file_path)
                        deleted_files.append(file_path)
                    except Exception as e:
                        self.stderr.write(f"Error deleting {file_path}: {e}")

        # 3. Summary
        self.stdout.write(f"Deleted {len(deleted_files)} unreferenced files.")
        for f in deleted_files:
            self.stdout.write(f"Deleted: {f}")
"""

"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from service_auth.user_profile.models import Profile, Media

class Command(BaseCommand):
    help = 'Deletes unreferenced media files from profile_picture, cover_photo, and media.file, excluding thumbnails.'

    def handle(self, *args, **kwargs):
        media_root = settings.MEDIA_ROOT
        thumbnail_dir = os.path.join(media_root, 'thumbnails')

        # 1. Get all referenced files
        referenced_files = set()

        for profile in Profile.objects.all():
            if profile.profile_picture:
                referenced_files.add(os.path.abspath(profile.profile_picture.path))
            if profile.cover_photo:
                referenced_files.add(os.path.abspath(profile.cover_photo.path))

        for media in Media.objects.all():
            if media.file:
                referenced_files.add(os.path.abspath(media.file.path))

        # 2. Walk through media root and delete unreferenced files (except thumbnails)
        deleted_files = []
        for root, dirs, files in os.walk(media_root):
            for file in files:
                file_path = os.path.abspath(os.path.join(root, file))

                # Skip thumbnails directory
                if os.path.commonpath([file_path, thumbnail_dir]) == thumbnail_dir:
                    continue

                if file_path not in referenced_files:
                    try:
                        os.remove(file_path)
                        deleted_files.append(file_path)
                    except Exception as e:
                        self.stderr.write(f"Error deleting {file_path}: {e}")

        # 3. Summary
        self.stdout.write(f"Deleted {len(deleted_files)} unreferenced files.")
        for f in deleted_files:
            self.stdout.write(f"Deleted: {f}")

"""


import os
from django.core.management.base import BaseCommand
from django.conf import settings
from service_auth.user_profile.models import Profile, Media

class Command(BaseCommand):
    help = 'Deletes unreferenced media files from profile_picture, cover_photo, and media.file, excluding thumbnails and files in uploads/.'

    def handle(self, *args, **kwargs):
        media_root = settings.MEDIA_ROOT
        thumbnail_dir = os.path.join(media_root, 'thumbnails')
        uploads_dir = os.path.join(media_root, 'uploads')

        # 1. Get all referenced files
        referenced_files = set()

        for profile in Profile.objects.all():
            if profile.profile_picture:
                referenced_files.add(os.path.abspath(profile.profile_picture.path))
            if profile.cover_photo:
                referenced_files.add(os.path.abspath(profile.cover_photo.path))

        for media in Media.objects.all():
            if media.file:
                referenced_files.add(os.path.abspath(media.file.path))

        # 2. Walk through media root and delete unreferenced files
        deleted_files = []
        for root, dirs, files in os.walk(media_root):
            for file in files:
                file_path = os.path.abspath(os.path.join(root, file))

                # Skip files in thumbnails/ and uploads/
                if os.path.commonpath([file_path, thumbnail_dir]) == thumbnail_dir:
                    continue
                if os.path.commonpath([file_path, uploads_dir]) == uploads_dir:
                    continue

                if file_path not in referenced_files:
                    try:
                        os.remove(file_path)
                        deleted_files.append(file_path)
                    except Exception as e:
                        self.stderr.write(f"Error deleting {file_path}: {e}")

        # 3. Summary
        self.stdout.write(f"Deleted {len(deleted_files)} unreferenced files.")
        for f in deleted_files:
            self.stdout.write(f"Deleted: {f}")

