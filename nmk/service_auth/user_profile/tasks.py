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
from django.core.files.uploadedfile import SimpleUploadedFile

from django.core.files.storage import default_storage

from django.utils.timezone import now
from django.db import transaction
from sklearn import logger
from .models import Media, Profile
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

from django.db.models import Count

from .utils import set_trending_score
from django.db.models import F
from math import pow, exp
from django.core.cache import cache

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




#worked for both video and image upload using mp4 format and also creationg thumbnails for video 
@shared_task(bind=True, max_retries=3, soft_time_limit=240, time_limit=70, acks_late=True)
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
                    "-vf", "scale='min(1280,iw)':-2",  #new
                    "-c:v", "libx264",
                    "-preset", "medium",
                    #"-crf", "28",
                    "-crf", "32",    #new
                    "-profile:v", "baseline",   #new
                    "-level", "3.1",    #new
                    "-pix_fmt", "yuv420p",    #new
                ]

                if has_audio:
                    #ffmpeg_cmd += ["-c:a", "aac", "-b:a", "128k"]
                    ffmpeg_cmd += ["-c:a", "aac", "-b:a", "96k"]
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
                    "ffmpeg",
                    "-ss", "00:00:01.000",
                    "-i", temp_file_path,   #before -ss Huge speedup on long videos
                    "-vframes", "1",
                    #"-an",    #Small CPU savings
                    "-q:v", "4",   #previously 2
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




@shared_task(bind=True, max_retries=3, soft_time_limit=130, time_limit=70, acks_late=True)
def process_profile_images(self, profile_id):
    try:
        try:
            profile = Profile.objects.get(id=profile_id)
        except ObjectDoesNotExist:
            logger.error(f"Profile {profile_id} not found. Will not retry.")
            return

        storage = CompressedMediaStorage()

        def process_image(image_field, output_size=(800, 800)):
            if not image_field:
                return None

            # Open existing image
            with default_storage.open(image_field.name, 'rb') as f:
                image = Image.open(f)

                # === Handle EXIF orientation like your main media task ===
                try:
                    exif = image._getexif()
                    if exif:
                        orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                        if orientation_key and orientation_key in exif:
                            orientation = exif[orientation_key]
                            rotate_values = {3: 180, 6: 270, 8: 90}
                            if orientation in rotate_values:
                                image = image.rotate(rotate_values[orientation], expand=True)
                                logger.info(f"Rotated image by {rotate_values[orientation]}° for {image_field.name}")
                except Exception as e:
                    logger.warning(f"EXIF rotation failed for profile image {profile_id}: {e}")

                # === Resize and convert to WebP ===
                image = storage.resize_image(image)
                image.thumbnail(output_size, Image.LANCZOS)

                if image.mode == "RGBA":
                    image = image.convert("RGB")

                buffer = BytesIO()
                image.save(buffer, format='WEBP', quality=storage.image_quality)
                buffer.seek(0)

                webp_name = os.path.splitext(image_field.name)[0] + ".webp"

                # Delete original image if exists
                if storage.exists(image_field.name):
                    try:
                        storage.delete(image_field.name)
                        logger.info(f"Deleted original image from R2: {image_field.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete original image from R2: {e}")

                return ContentFile(buffer.read(), name=webp_name)

        # Process profile picture
        if profile.profile_picture:
            logger.info(f"Processing profile picture for user {profile.user.username}")
            processed_pic = process_image(profile.profile_picture, output_size=(400, 400))
            if processed_pic:
                profile.profile_picture.save(processed_pic.name, processed_pic, save=False)

        # Process cover photo
        if profile.cover_photo:
            logger.info(f"Processing cover photo for user {profile.user.username}")
            processed_cover = process_image(profile.cover_photo, output_size=(1280, 720))
            if processed_cover:
                profile.cover_photo.save(processed_cover.name, processed_cover, save=False)

        profile.save()
        logger.info(f"Profile images processed successfully for user {profile.user.username}")

    except SoftTimeLimitExceeded:
        logger.error(f"Profile image task exceeded time limit for profile {profile_id}")
        return

    except Exception as e:
        logger.error(f"Failed to process profile images for profile {profile_id}: {e}")
        self.retry(exc=e)


#____________________________________
#for trending score updateion refer to the util and model engagement class
#________________________________________
'''
@shared_task
def update_trending_scores():
    """Recalculate trending scores and push to Redis."""
    now = timezone.now()

    for media in Media.objects.select_related('engagements').all():
        e = media.engagements.first()
        if not e:
            continue
        
        age_hours = (now - e.created_at).total_seconds() / 3600
        α, β, γ, decay = 3.0, 5.0, 1.0, 1.3
        score = (α * e.likes + β * e.comments + γ * e.views) / pow((age_hours + 2), decay)
        set_trending_score(media.id, score)
'''
#_____________________________________________


#_________________________________
#
#for trending score updation refer to the (calculate_media_socre in views)
#(set_trending_score in utils) 
#and model-engagement class
#_________________________________

@shared_task
def update_trending_scores():
    """
    Periodically updates trending scores for recent media (past 7 days),
    based on likes, comments, views, and shares, applying exponential time decay.
    Uses numeric counters (fields or cached values) instead of related managers
    for scalability and to avoid AttributeErrors.
    """
    now = timezone.now()
    media_list = Media.objects.filter(created_at__gte=now - timedelta(days=7))

    updated_count = 0

    for media in media_list:
        # --- Get safe numeric counters (default to 0 if missing) ---
        like_count = getattr(media, "likes_count", 0)
        comment_count = getattr(media, "comment_count", 0)
        view_count = getattr(media, "view_count", 0)
        share_count = getattr(media, "shares_count", 0)

        # --- Weighted scoring ---
        like_score = like_count * 1.0
        comment_score = comment_count * 2.0
        view_score = view_count * 0.2
        share_score = share_count * 3.0

        raw_score = like_score + comment_score + view_score + share_score

        # --- Exponential decay based on media age ---
        hours_old = (now - media.created_at).total_seconds() / 3600
        decay_factor = exp(-0.02 * hours_old)
        decayed_score = raw_score * decay_factor

        # --- Cache individual component scores for insight/debugging ---
        cache.set(f"trending_like_score:{media.id}", like_score, timeout=10800)
        cache.set(f"trending_comment_score:{media.id}", comment_score, timeout=10800)
        cache.set(f"trending_view_score:{media.id}", view_score, timeout=10800)
        cache.set(f"trending_share_score:{media.id}", share_score, timeout=10800)

        # --- Cache total trending score ---
        cache.set(f"trending_score:{media.id}", decayed_score, timeout=10800)

        updated_count += 1

    return f"{updated_count} trending scores updated successfully"

#__________________________________
#
#
#
#__________________________________

