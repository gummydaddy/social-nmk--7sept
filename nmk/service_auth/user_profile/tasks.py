# service_auth/user_profile/tasks.py

import os
import subprocess
import tempfile
import io
import logging
from django.utils import timezone
from datetime import timedelta
from PIL import Image, ImageFilter, ImageOps
from django.core.files.base import ContentFile

from celery import shared_task
from django.utils.timezone import now
from django.db import transaction
from sklearn import logger
from .models import Media
from .storage import CompressedMediaStorage
from service_auth.user_profile.models import Story
from django.apps import apps  # Lazy import
from .storage import CompressedMediaStorage
import numpy as np
from django.conf import settings
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

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

"""
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
"""

"""
#best w3orking yet5may
@shared_task(bind=True, max_retries=3)
def process_media_upload(self, media_id, file_name, media_type, filter_name=None):
    temp_file_path = None  # Initialize variable

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
            with open(temp_file_path, 'rb') as original_file:
                media.file.save(file_name, ContentFile(original_file.read()), save=True)

        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        if temp_file_path and isinstance(temp_file_path, (str, bytes, os.PathLike)) and os.path.exists(temp_file_path):
            try:
                logger.debug(f"Attempting to delete temporary file at path: {repr(temp_file_path)}")
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"Failed to delete temporary file {temp_file_path}: {e}")

        #if temp_file_path and os.path.exists(temp_file_path):
            #try:
                #os.remove(temp_file_path)
            #except Exception as e:
                #logger.error(f"Failed to delete temporary file {temp_file_path}: {e}")
        #if os.path.exists(temp_file_path):
            #os.remove(temp_file_path)
"""
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, file_name, media_type, filter_name=None):
    temp_file_path = None  # Initialize variable for cleanup in finally block

    try:
        media = Media.objects.get(id=media_id)

        if media.is_processed:
            logger.info(f"Media {media_id} already processed. Skipping.")
            return

        storage = CompressedMediaStorage()

        # Save media to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            for chunk in media.file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Process image
        if media_type == 'image':
            image = Image.open(temp_file_path)

            # Apply optional filter
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

            # Compress and save
            byte_io = io.BytesIO()
            image = storage.resize_image(image)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            image.save(byte_io, format='JPEG', quality=storage.image_quality)
            media.file.save(file_name, ContentFile(byte_io.getvalue()), save=True)

        # Process video
        elif media_type == 'video':
            with open(temp_file_path, 'rb') as original_file:
                media.file.save(file_name, ContentFile(original_file.read()), save=True)

        media.is_processed = True
        media.save(update_fields=['is_processed'])

        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        # Optionally, mark the media object as failed
        return

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        if temp_file_path and isinstance(temp_file_path, (str, bytes, os.PathLike)) and os.path.exists(temp_file_path):
            try:
                logger.debug(f"Attempting to delete temporary file at path: {repr(temp_file_path)}")
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"Failed to delete temporary file {temp_file_path}: {e}")

"""

@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70)
def process_media_upload(self, media_id, file_name, media_type, filter_name=None):
    temp_file_path = None

    try:
        media = Media.objects.get(id=media_id)
        if media.is_processed:
            logger.info(f"Media {media_id} already processed. Skipping.")
            return

        storage = CompressedMediaStorage()

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            for chunk in media.file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        if media_type == 'image':
            image = Image.open(temp_file_path)

            # Optional filter
            if filter_name:
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

            # Compress and re-save image
            byte_io = io.BytesIO()
            image = storage.resize_image(image)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            image.save(byte_io, format='JPEG', quality=storage.image_quality)
            media.file.save(file_name, ContentFile(byte_io.getvalue()), save=True)

            # --- Generate thumbnail ---
            thumb_io = io.BytesIO()
            thumbnail = image.copy()
            thumbnail.thumbnail((250, 150))
            thumbnail.save(thumb_io, format='JPEG', quality=85)
            thumb_name = f"thumb_{os.path.basename(file_name)}"
            media.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=False)

        elif media_type == 'video':
            with open(temp_file_path, 'rb') as original_file:
                media.file.save(file_name, ContentFile(original_file.read()), save=True)
            # Add future: extract video thumbnail here

        media.is_processed = True
        media.save(update_fields=['file', 'thumbnail', 'is_processed'])

        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit for media: {file_name}")
        return

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"Failed to delete temp file {temp_file_path}: {e}")
"""



'''

@shared_task(bind=True, max_retries=2)
def generate_thumbnail_task(self, media_id):
    """Generate a thumbnail asynchronously for images or videos."""
    try:
        Media = apps.get_model('user_profile', 'Media')  # Dynamically fetch model
        media = Media.objects.get(id=media_id)

        if not media.file:
            logger.warning(f"Media {media_id} has no associated file.")
            return

        file_path = media.file.path
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return

        # Generate Image Thumbnail
        if media.file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            img = Image.open(file_path)
            img.thumbnail((250, 150))

            thumb_io = io.BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(thumb_io, format=img_format, quality=85)

            thumb_name = f"thumb_{os.path.basename(media.file.name)}"
            media.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=True)

        # Generate Video Thumbnail
        elif media.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            clip = VideoFileClip(file_path)
            frame = clip.get_frame(1)  # Capture a frame at 1 second
            img = Image.fromarray(np.uint8(frame))
            img.thumbnail((250, 150))

            thumb_io = io.BytesIO()
            img.save(thumb_io, format="JPEG", quality=85)

            thumb_name = f"thumb_{os.path.splitext(os.path.basename(media.file.name))[0]}.jpg"
            media.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=True)

            # Close the video clip to prevent memory leaks
            clip.close()

        logger.info(f"Thumbnail successfully created for {media.file.name}")

    except Media.DoesNotExist:
        logger.error(f"Media object with ID {media_id} does not exist.")
    except Exception as e:
        logger.exception(f"Error generating thumbnail for media {media_id}: {e}")
        self.retry(exc=e)  # Retry task if an error occurs
'''
