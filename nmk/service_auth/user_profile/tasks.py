# service_auth/user_profile/tasks.py

import os
import subprocess
import tempfile
import io
import logging
from django.utils import timezone
from datetime import timedelta
from PIL import Image, ImageFilter, ImageOps, ExifTags
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

#import pillow_heif
#pillow_heif.register_heif_opener()


logger = logging.getLogger(__name__)


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
#@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True, queue='media_upload')


@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, temp_file_path, file_name, media_type, filter_name=None):
    try:
        media = Media.objects.get(id=media_id)

        if media.is_processed:
            logger.info(f"Media {media_id} already processed. Skipping.")
            return

        storage = CompressedMediaStorage()

        if media_type == 'image':
            logger.info(f"Processing image from: {temp_file_path}")
            image = Image.open(temp_file_path)

            # --- Handle EXIF Orientation ---
            try:
                exif = image._getexif()
                if exif:
                    orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                    if orientation_key and orientation_key in exif:
                        orientation = exif[orientation_key]
                        rotate_values = {3: 180, 6: 270, 8: 90}
                        if orientation in rotate_values:
                            image = image.rotate(rotate_values[orientation], expand=True)
                            logger.info(f"Rotated image by {rotate_values[orientation]}°")
            except Exception as e:
                logger.warning(f"EXIF rotation failed for media {media.id}: {e}")

            # Optional filter
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

            # Resize and convert to WEBP
            byte_io = io.BytesIO()
            image = storage.resize_image(image)
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            webp_filename = os.path.splitext(file_name)[0] + ".webp"
            image.save(byte_io, format='WEBP', quality=storage.image_quality)

            # Save .webp to model
            media.file.save(webp_filename, ContentFile(byte_io.getvalue()), save=False)

            # Delete the original uploaded file (jpg/png etc.)
            original_file_path = media.file.path.replace(".webp", os.path.splitext(file_name)[1])
            if os.path.exists(original_file_path):
                try:
                    os.remove(original_file_path)
                    logger.info(f"Deleted original uploaded file: {original_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete original file {original_file_path}: {e}")

        elif media_type == 'video':
            # (unchanged)
            with open(temp_file_path, 'rb') as original_file:
                media.file.save(file_name, ContentFile(original_file.read()), save=False)

        media.is_processed = True
        media.save(update_fields=['file', 'is_processed'])
        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        return

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"Deleted temp file: {temp_file_path}")
        except Exception as e:
            logger.error(f"Failed to delete temporary file {temp_file_path}: {e}")

