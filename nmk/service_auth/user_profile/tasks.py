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
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import File

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
#directly upload video no compression 
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, temp_file_path, file_name, media_type, filter_name=None):
    try:
        try:
            media = Media.objects.get(id=media_id)
        except ObjectDoesNotExist:
            logger.error(f"Media {media_id} not found. Will not retry.")
            return  # Do not retry — silent fail or notify manually
        #media = Media.objects.get(id=media_id)

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
                if filter_name == 'sepia':
                    image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                elif filter_name == 'grayscale':
                    image = ImageOps.grayscale(image)
                elif filter_name == 'invert':
                    image = ImageOps.invert(image)
                else:
                    image = image.filter(ImageFilter.EMBOSS)

            # Resize and convert to .webp
            image = storage.resize_image(image)
            if image.mode == "RGBA":
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format='WEBP', quality=storage.image_quality)
            buffer.seek(0)

            # Create .webp filename
            webp_filename = os.path.splitext(file_name)[0] + ".webp"

            # Delete original file from bucket if it was saved automatically earlier
            if media.file and media.file.name and storage.exists(media.file.name):
                try:
                    storage.delete(media.file.name)
                    logger.info(f"Deleted pre-saved original file from R2: {media.file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original file from R2: {e}")

            # Save the processed .webp image only
            media.file.save(webp_filename, ContentFile(buffer.read()), save=False)

        elif media_type == 'video':
            with open(temp_file_path, 'rb') as original_file:
                media.file.save(file_name, ContentFile(original_file.read()), save=False)

        media.is_processed = True
        media.save(update_fields=['file', 'is_processed'])
        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        return

    except ObjectDoesNotExist:
        logger.error(f"Media {media_id} not found. Will not retry.")
        return  # Final fallback for unexpected object deletion during task runtime

    except Exception as e:
        logger.error(f"Failed to process {media_type} {file_name}: {e}")
        self.retry(exc=e)

    finally:
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"Deleted temp file: {temp_file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")

"""


'''
#worked well was using webm formating didnt work for video upload
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, temp_file_path, file_name, media_type, filter_name=None):
    try:
        try:
            media = Media.objects.get(id=media_id)
        except ObjectDoesNotExist:
            logger.error(f"Media {media_id} not found. Will not retry.")
            return

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
                if filter_name == 'sepia':
                    image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                elif filter_name == 'grayscale':
                    image = ImageOps.grayscale(image)
                elif filter_name == 'invert':
                    image = ImageOps.invert(image)
                else:
                    image = image.filter(ImageFilter.EMBOSS)

            # Resize and convert to .webp
            image = storage.resize_image(image)
            if image.mode == "RGBA":
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format='WEBP', quality=storage.image_quality)
            buffer.seek(0)

            webp_filename = os.path.splitext(file_name)[0] + ".webp"

            if media.file and media.file.name and storage.exists(media.file.name):
                try:
                    storage.delete(media.file.name)
                    logger.info(f"Deleted pre-saved original file from R2: {media.file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original file from R2: {e}")

            media.file.save(webp_filename, ContentFile(buffer.read()), save=False)

        elif media_type == 'video':
            import subprocess

            webm_filename = os.path.splitext(file_name)[0] + ".webm"
            webm_output_path = os.path.join("/tmp", webm_filename)

            try:
                logger.info(f"Converting video {file_name} to .webm using FFmpeg")

                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", temp_file_path,
                    "-c:v", "libvpx",           # VP8 video codec
                    #"-c:v", "libvpx-vp9",            # VP8 video codec
                    "-b:v", "1M",
                    #"-crf", "32",                 # Lower CRF = better quality, higher = more compression
                    #"-b:v", "0",              # Bitrate: adjust as needed
                    "-c:a", "libvorbis",
                    #"-b:a", "64k",       # Vorbis audio codec
                    "-threads", "2",
                    "-deadline", "realtime",   # Faster encoding
                    "-y",                      # Overwrite output
                    webm_output_path
                ]

                subprocess.run(ffmpeg_cmd, check=True)

                # Delete any pre-saved original video from R2 bucket
                if media.file and media.file.name and storage.exists(media.file.name):
                    try:
                        storage.delete(media.file.name)
                        logger.info(f"Deleted pre-saved original file from R2: {media.file.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete original file from R2: {e}")

                # Save .webm video to bucket
                with open(webm_output_path, 'rb') as f:
                    #media.file.save(webm_filename, ContentFile(f.read()), save=False)
                    media.file.save(webm_filename, File(f, name=webm_filename), save=False)

                # Clean up temporary .webm file
                if os.path.exists(webm_output_path):
                    os.remove(webm_output_path)
                    logger.debug(f"Deleted temp webm file: {webm_output_path}")

            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg failed to convert {file_name} to .webm: {e}")
                raise self.retry(exc=e)
            except Exception as e:
                logger.error(f"Unexpected error during video conversion: {e}")
                raise self.retry(exc=e)

        media.is_processed = True
        media.save(update_fields=['file', 'is_processed'])
        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        return

    except ObjectDoesNotExist:
        logger.error(f"Media {media_id} not found. Will not retry.")
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
            logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")


'''

"""
#worked for both image and videop upload uploaded video in mp4 format did not create thumbnails 
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, temp_file_path, file_name, media_type, filter_name=None):
    try:
        try:
            media = Media.objects.get(id=media_id)
        except ObjectDoesNotExist:
            logger.error(f"Media {media_id} not found. Will not retry.")
            return

        if media.is_processed:
            logger.info(f"Media {media_id} already processed. Skipping.")
            return

        storage = CompressedMediaStorage()

        if media_type == 'image':
            logger.info(f"Processing image from: {temp_file_path}")
            image = Image.open(temp_file_path)

            # Handle EXIF Orientation
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

            # Optional filters
            if filter_name:
                logger.info(f"Applying filter: {filter_name}")
                if filter_name == 'sepia':
                    image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                elif filter_name == 'grayscale':
                    image = ImageOps.grayscale(image)
                elif filter_name == 'invert':
                    image = ImageOps.invert(image)
                else:
                    image = image.filter(ImageFilter.EMBOSS)

            # Resize and convert to .webp
            image = storage.resize_image(image)
            if image.mode == "RGBA":
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format='WEBP', quality=storage.image_quality)
            buffer.seek(0)

            webp_filename = os.path.splitext(file_name)[0] + ".webp"

            if media.file and media.file.name and storage.exists(media.file.name):
                try:
                    storage.delete(media.file.name)
                    logger.info(f"Deleted original image from R2: {media.file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original image from R2: {e}")

            media.file.save(webp_filename, ContentFile(buffer.read()), save=False)

        elif media_type == 'video':
            mp4_filename = os.path.splitext(file_name)[0] + "_compressed.mp4"
            mp4_output_path = os.path.join(tempfile.gettempdir(), mp4_filename)

            try:
                logger.info(f"Compressing video {file_name} to .mp4 using FFmpeg")

                # Detect if audio stream exists
                has_audio = False
                try:
                    probe_cmd = [
                        "ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=codec_type",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        temp_file_path
                    ]
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    has_audio = 'audio' in result.stdout.strip().lower()
                except Exception as e:
                    logger.warning(f"FFprobe failed to check audio stream: {e}")

                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", temp_file_path,
                    "-c:v", "libx264",
                    "-preset", "fast",             # good speed/quality balance
                    "-crf", "28",                  # lower = better quality, higher = more compression
                ]

                if has_audio:
                    ffmpeg_cmd += ["-c:a", "aac", "-b:a", "128k"]
                else:
                    ffmpeg_cmd += ["-an"]

                ffmpeg_cmd += [
                    "-movflags", "+faststart",     # improve streaming
                    "-y", mp4_output_path
                ]

                subprocess.run(ffmpeg_cmd, check=True)

                if media.file and media.file.name and storage.exists(media.file.name):
                    try:
                        storage.delete(media.file.name)
                        logger.info(f"Deleted original video from R2: {media.file.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete original video from R2: {e}")

                with open(mp4_output_path, 'rb') as f:
                    media.file.save(mp4_filename, File(f, name=mp4_filename), save=False)

                if os.path.exists(mp4_output_path):
                    os.remove(mp4_output_path)
                    logger.debug(f"Deleted temp mp4 file: {mp4_output_path}")

            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg failed to compress {file_name} to .mp4: {e}")
                raise self.retry(exc=e)
            except Exception as e:
                logger.error(f"Unexpected error during video compression: {e}")
                raise self.retry(exc=e)

        media.is_processed = True
        media.save(update_fields=['file', 'is_processed'])
        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        return

    except ObjectDoesNotExist:
        logger.error(f"Media {media_id} not found. Will not retry.")
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
            logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")

"""


#worked for both video and image upload using mp4 format and also creationg thumbnails for video 
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_media_upload(self, media_id, temp_file_path, file_name, media_type, filter_name=None):
    try:
        try:
            media = Media.objects.get(id=media_id)
        except ObjectDoesNotExist:
            logger.error(f"Media {media_id} not found. Will not retry.")
            return

        if media.is_processed:
            logger.info(f"Media {media_id} already processed. Skipping.")
            return

        storage = CompressedMediaStorage()

        if media_type == 'image':
            logger.info(f"Processing image from: {temp_file_path}")
            image = Image.open(temp_file_path)

            # Handle EXIF Orientation
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

            # Optional filters
            if filter_name:
                logger.info(f"Applying filter: {filter_name}")
                if filter_name == 'sepia':
                    image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                elif filter_name == 'grayscale':
                    image = ImageOps.grayscale(image)
                elif filter_name == 'invert':
                    image = ImageOps.invert(image)
                else:
                    image = image.filter(ImageFilter.EMBOSS)

            # Resize and convert to .webp
            image = storage.resize_image(image)
            if image.mode == "RGBA":
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format='WEBP', quality=storage.image_quality)
            buffer.seek(0)

            webp_filename = os.path.splitext(file_name)[0] + ".webp"

            if media.file and media.file.name and storage.exists(media.file.name):
                try:
                    storage.delete(media.file.name)
                    logger.info(f"Deleted original image from R2: {media.file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original image from R2: {e}")

            media.file.save(webp_filename, ContentFile(buffer.read()), save=False)

        elif media_type == 'video':
            mp4_filename = os.path.splitext(file_name)[0] + "_compressed.mp4"
            mp4_output_path = os.path.join(tempfile.gettempdir(), mp4_filename)

            try:
                logger.info(f"Compressing video {file_name} to .mp4 using FFmpeg")

                # Detect if audio stream exists
                has_audio = False
                try:
                    probe_cmd = [
                        "ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=codec_type",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        temp_file_path
                    ]
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    has_audio = 'audio' in result.stdout.strip().lower()
                except Exception as e:
                    logger.warning(f"FFprobe failed to check audio stream: {e}")

                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", temp_file_path,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "28",
                ]

                if has_audio:
                    ffmpeg_cmd += ["-c:a", "aac", "-b:a", "128k"]
                else:
                    ffmpeg_cmd += ["-an"]

                ffmpeg_cmd += [
                    "-movflags", "+faststart",
                    "-y", mp4_output_path
                ]

                subprocess.run(ffmpeg_cmd, check=True)

                if media.file and media.file.name and storage.exists(media.file.name):
                    try:
                        storage.delete(media.file.name)
                        logger.info(f"Deleted original video from R2: {media.file.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete original video from R2: {e}")

                with open(mp4_output_path, 'rb') as f:
                    media.file.save(mp4_filename, File(f, name=mp4_filename), save=False)

                if os.path.exists(mp4_output_path):
                    os.remove(mp4_output_path)
                    logger.debug(f"Deleted temp mp4 file: {mp4_output_path}")

                # === Generate Video Thumbnail ===
                thumb_filename = f"thumb_{os.path.splitext(file_name)[0]}.jpg"
                thumb_output_path = os.path.join(tempfile.gettempdir(), thumb_filename)

                thumb_cmd = [
                    "ffmpeg", "-i", temp_file_path,
                    "-ss", "00:00:01.000",
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y",
                    thumb_output_path
                ]
                subprocess.run(thumb_cmd, check=True)
                logger.info(f"Generated video thumbnail: {thumb_output_path}")

                with open(thumb_output_path, 'rb') as thumb_file:
                    thumb_content = ContentFile(thumb_file.read())
                    storage_thumb_path = f"thumbnails/{thumb_filename}"
                    media.thumbnail.save(storage_thumb_path, thumb_content, save=False)

                if os.path.exists(thumb_output_path):
                    os.remove(thumb_output_path)
                    logger.debug(f"Deleted temp video thumbnail file: {thumb_output_path}")

            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg failed to compress {file_name} or generate thumbnail: {e}")
                raise self.retry(exc=e)
            except Exception as e:
                logger.error(f"Unexpected error during video compression or thumbnail generation: {e}")
                raise self.retry(exc=e)

        media.is_processed = True
        media.save(update_fields=['file', 'thumbnail', 'is_processed'])
        logger.info(f"{media_type.capitalize()} {file_name} processed and uploaded successfully.")

    except SoftTimeLimitExceeded:
        logger.error(f"Task exceeded soft time limit and was terminated for media: {file_name}")
        return

    except ObjectDoesNotExist:
        logger.error(f"Media {media_id} not found. Will not retry.")
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
            logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")




