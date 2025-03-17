# service_auth/user_profile/tasks.py
import os
import subprocess
import tempfile
import io
import logging
from PIL import Image, ImageFilter, ImageOps
from django.core.files.base import ContentFile

from django.utils import timezone
from datetime import timedelta
from celery import shared_task
from django.utils.timezone import now
from django.db import transaction
from sklearn import logger
from service_auth.user_profile.models import Story
from .models import Media
from .storage import CompressedMediaStorage


# @shared_task
# def delete_expired_stories():
#     expired_stories = Story.objects.filter(created_at__lt=now() - timezone.timedelta(hours=24))
#     count = expired_stories.count()
#     for story in expired_stories:
#         # if story.media:
#         if story.media and story.media.file:  # Check if media has a file
#             # story.media.delete_file()  # Optional: Delete the associated file
#             story.media.file.delete(save=True)  # Delete the media file from storage
#         story.delete()
#     return f"Deleted {count} expired stories."


@shared_task
def delete_expired_stories():
    expired_stories = Story.objects.filter(created_at__lt=now() - timezone.timedelta(hours=24))
    count = expired_stories.count()

    # Use a transaction to ensure consistency
    with transaction.atomic():
        for story in expired_stories:
            # Delete associated media instance if it exists
            if story.media:
                try:
                    # Delete the media file from storage
                    story.media.file.delete(save=False)
                    
                    # Delete the media instance
                    story.media.delete()
                except Exception as e:
                    logger.error(f"Error deleting media for story {story.id}: {e}")

            # Delete the story instance
            story.delete()

    return f"Deleted {count} expired stories and their associated media."



@shared_task(bind=True, max_retries=3)
def process_media_upload(self, media_id, file_name, media_type, filter_name=None):
    try:
        media = Media.objects.get(id=media_id)
        storage = CompressedMediaStorage()

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            for chunk in media.file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        if media_type == 'image':
            image = Image.open(temp_file_path)
            if filter_name:
                logger.info(f"Applying filter: {filter_name}")
                filter_map = {
                    'clarendon': ImageFilter.EMBOSS,
                    'sepia': 'sepia',
                    'grayscale': 'grayscale',
                    'invert': ImageOps.invert,
                }
                if filter_name == 'sepia':
                    image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                elif filter_name == 'grayscale':
                    image = ImageOps.grayscale(image)
                else:
                    image = image.filter(filter_map.get(filter_name, ImageFilter.BLUR))

            # Save compressed image
            byte_io = io.BytesIO()
            image = storage.resize_image(image)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            image.save(byte_io, format='JPEG', quality=storage.image_quality)
            media.file.save(file_name, ContentFile(byte_io.getvalue()), save=True)

        elif media_type == 'video':
            output_path = temp_file_path + "_compressed.mp4"
            command = [
                'ffmpeg', '-i', temp_file_path,
                '-vcodec', 'libx264', '-crf', str(storage.video_crf),
                '-preset', 'slow', '-y',
                output_path
            ]
            subprocess.run(command, check=True)
            with open(output_path, 'rb') as compressed_file:
                media.file.save(file_name, ContentFile(compressed_file.read()), save=True)
            os.remove(output_path)

        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)