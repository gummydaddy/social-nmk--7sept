# service_auth/user_profile/tasks.py
import os
import subprocess
import tempfile
import io
import logging
import math
import time

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

from django.db.models import F, Count, Q, Exists, OuterRef

from .utils import set_trending_score
from .utils import TRENDING_ZSET_KEY, TRENDING_WINDOW_DAYS


from django.db.models import F
from math import pow, exp
from django.core.cache import cache

from django_redis import get_redis_connection

from collections import defaultdict

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




#worked for both video and image upload using mp4 format and also creationg thumbnails for video 
@shared_task(bind=True, max_retries=3, soft_time_limit=600, time_limit=600, acks_late=True)
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

                    "-ss", "0",

                    "-i", temp_file_path,
                    "-vf", "scale='min(1280,iw)':-2",  #new
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "28",
                    #"-crf", "32",    #new

                    "-tune", "fastdecode",        #  faster playback

                    #"-profile:v", "baseline",   #new
                    "-profile:v", "main",

                    #"-level", "3.1",    #new
                    "-pix_fmt", "yuv420p",    #new

                    # THREAD OPTIMIZATION
                    "-threads", "0",              # auto CPU usage
                ]

                if has_audio:
                    #ffmpeg_cmd += ["-c:a", "aac", "-b:a", "128k"]
                    ffmpeg_cmd += ["-c:a", "aac", "-b:a", "96k", "-ac", "2"]
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
                    #"-ss", "00:00:01.000",
                    "-ss", "1",

                    "-i", temp_file_path,   #before -ss Huge speedup on long videos
                    #"-vframes", "1",
                    "-frames:v", "1",
                    #"-an",    #Small CPU savings
                    "-q:v", "4",   #previously 2
                    "-update", "1",

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

        # ---------------------------
        # STORE MEDIA → CREATOR IN REDIS
        # ---------------------------
        try:
            from django_redis import get_redis_connection
            redis = get_redis_connection("default")

            redis.set(f"media:creator:{media.id}", media.user_id)

            logger.info(
                f"Stored media:creator:{media.id} → {media.user_id} in Redis"
            )
        except Exception as e:
            logger.warning(
                f"Failed to store media:creator mapping for media {media.id}: {e}"
            )


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



#_________________________________
#
#for trending score updation refer to the (calculate_media_socre in views)
#(set_trending_score in utils) 
#and model-engagement class
#_________________________________
'''
TRENDING_ZSET_KEY = "trending_media_scores"


'''



@shared_task
def update_trending_scores():
    """
    Celery task to update trending scores for all recent media.
    Should be run periodically (e.g., every 15-30 minutes).
    """
    now = timezone.now()
    redis_conn = get_redis_connection("default")

    try:
        # --------------------------------------------------
        # STEP 1: Remove media older than trending window
        # --------------------------------------------------
        cutoff = now - timedelta(days=TRENDING_WINDOW_DAYS)
        #old_media_ids = Media.objects.filter(
            #created_at__lt=cutoff
        #).values_list("id", flat=True)

        old_media_ids = list(
            Media.objects.filter(created_at__lt=cutoff)
            .values_list("id", flat=True)[:300]
        )


        if old_media_ids:
            removed = redis_conn.zrem(TRENDING_ZSET_KEY, *[str(i) for i in old_media_ids])
            logger.info(f"Removed {removed} old media from trending cache")

        # --------------------------------------------------
        # STEP 2: Fetch recent media to score
        # --------------------------------------------------
        media_list = (
            Media.objects.filter(
                created_at__gte=cutoff,
                is_private=False  # Only public media in trending
            )
            .annotate(
                likes_count=Count("likes", distinct=True),
                comment_count=Count("comments", distinct=True),
                saves_count=Count("saved_by_users", distinct=True),
            )
            .only("id", "created_at", "view_count")
        )

        updated_count = 0
        scores_dict = {}

        # --------------------------------------------------
        # STEP 3: Calculate trending scores
        # --------------------------------------------------
        for media in media_list:
            like_count = media.likes_count or 0
            comment_count = media.comment_count or 0
            save_count = media.saves_count or 0
            view_count = media.view_count or 0

            # Weighted scoring
            raw_score = (
                like_count * 1.6 +
                comment_count * 2.0 +
                save_count * 3.0 +
                view_count * 0.3
            )

            # Time decay (exponential decay based on age)
            hours_old = (now - media.created_at).total_seconds() / 3600
            decayed_score = raw_score * exp(-0.07 * hours_old)

            scores_dict[str(media.id)] = decayed_score
            updated_count += 1

        # --------------------------------------------------
        # STEP 4: Batch update Redis (more efficient)
        # --------------------------------------------------
        if scores_dict:
            redis_conn.zadd(TRENDING_ZSET_KEY, scores_dict)
            logger.info(f"Updated {updated_count} trending scores in batch")

        # --------------------------------------------------
        # STEP 5: Set expiry for the entire sorted set
        # --------------------------------------------------
        redis_conn.expire(TRENDING_ZSET_KEY, 60 * 60 * 24 * 3)  # 3 days

        return f"{updated_count} trending scores updated successfully"

    except Exception as e:
        logger.exception(f"Error updating trending scores: {e}")
        return f"Error: {str(e)}"



@shared_task
def remove_private_media_from_trending():
    """
    Remove private media from trending cache (hourly safety check).
    
    Privacy Rules Enforced:
    1. Media marked as private (is_private=True) → REMOVED
    2. Media from users with private profiles → REMOVED
    
    This runs periodically as a safety net. The instant updates in
    toggle_privacy and toggle_media_privacy handle most cases immediately.
    """
    try:
        from service_auth.user_profile.models import Media
        
        redis_conn = get_redis_connection("default")
        
        # Get all media IDs in trending
        all_trending_ids = redis_conn.zrange(TRENDING_ZSET_KEY, 0, -1)
        
        if not all_trending_ids:
            logger.info("No trending media to check")
            return "No trending media to check"
        
        # Convert bytes to integers
        trending_ids = [int(mid) for mid in all_trending_ids]
        
        # Find media that should be removed (EITHER condition removes from trending)
        private_media_ids = Media.objects.filter(
            id__in=trending_ids
        ).filter(
            Q(is_private=True) |  #  Rule 1: Media is private
            Q(user__profile__is_private=True)  #  Rule 2: User profile is private
        ).values_list('id', flat=True)
        
        if private_media_ids:
            removed = redis_conn.zrem(
                TRENDING_ZSET_KEY,
                *[str(mid) for mid in private_media_ids]
            )
            logger.info(
                f"Removed {removed} private media from trending cache "
                f"(media private: {removed} items OR user profile private)"
            )
            return f"Removed {removed} private media from trending"
        
        logger.info("No private media found in trending (all clean)")
        return "No private media found in trending"
        
    except Exception as e:
        logger.exception(f"Error removing private media from trending: {e}")
        return f"Error: {str(e)}"
 

#_________________________________
#
#
#__________________________________



#_____________________________________________________________________
#
#new task to setup for displaying similar media to users with similar iterest
#making the platform stronger and more attractive to the users providing similar
#interest based media to users
#_____________________________________________________________________

WINDOW_SECONDS = 10 * 24 * 60 * 60

MAX_SIMILAR_USERS = 100
MAX_RECO_ITEMS = 150

MIN_OVERLAP = 2
MIN_USER_VIEWS = 2

TRENDING_WEIGHT = 0.7
COLLAB_WEIGHT = 1.5


# Penalty multipliers (add at top of file)
PENALTY_SAME_CREATOR = 0.3  # 70% reduction (shows 20% of original score)
PENALTY_SAME_CATEGORY = 0.7  # 30% reduction
PENALTY_SIMILAR_MEDIA = 0.6  # 40% reduction
PENALTY_SAME_HASHTAGS = 0.9  # 10% reduction


def time_decay(view_ts, now):
    hours_ago = (now - view_ts) / 3600
    #return max(0.2, 1 - (hours_ago / 30))
    return max(0.2, math.exp(-hours_ago / 24))


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
)
def build_user_recommendations_WITH_BLOCK_FILTER(self, user_id):
    """
    Enhanced version that filters blocked users from recommendations
    """
    redis = get_redis_connection("default")
    now = int(time.time())
    cutoff = now - WINDOW_SECONDS

    user_key = f"user:viewed:{user_id}"
    reco_key = f"user:reco:{user_id}"

    # ---------------------------
    # GET BLOCKED USERS (NEW)
    # ---------------------------
    from service_auth.notion.models import Follow, Notification, Comment, Hashtag, BlockedUser
    
    # Users this user blocked
    users_i_blocked = set(
        BlockedUser.objects.filter(blocker_id=user_id).values_list('blocked_id', flat=True)
    )
    
    # Users who blocked this user
    users_who_blocked_me = set(
        BlockedUser.objects.filter(blocked_id=user_id).values_list('blocker_id', flat=True)
    )
    
    all_blocked_users = users_i_blocked | users_who_blocked_me

    # ---------------------------
    # USER HISTORY
    # ---------------------------
    user_media = redis.zrangebyscore(
        user_key, cutoff, now, withscores=True
    )

    redis.delete(reco_key)

    # ---------------------------
    # COLD START
    # ---------------------------
    if len(user_media) < MIN_USER_VIEWS:
        trending = redis.zrevrange(
            TRENDING_ZSET_KEY,
            0, MAX_RECO_ITEMS - 1, withscores=True
        )
        
        # Filter blocked users' media from trending
        if trending and all_blocked_users:
            from .models import Media
            trending_ids = [int(mid) for mid, _ in trending]
            
            # Get which trending media are from blocked users
            blocked_media = Media.objects.filter(
                id__in=trending_ids,
                user_id__in=all_blocked_users
            ).values_list('id', flat=True)
            
            # Remove blocked media from trending
            trending = [(mid, score) for mid, score in trending 
                       if int(mid) not in blocked_media]
        
        if trending:
            redis.zadd(
                reco_key,
                {mid.decode(): score for mid, score in trending}
            )
        return "cold_start"

    user_media_ids = {mid.decode() for mid, _ in user_media}

    # ---------------------------
    # FIND SIMILAR USERS (EXCLUDE BLOCKED)
    # ---------------------------
    overlap_counter = defaultdict(int)

    for media_id, _ in user_media:
        viewers = redis.zrangebyscore(
            f"media:viewed_by:{media_id.decode()}",
            cutoff,
            now
        )
        for viewer in viewers:
            viewer_id = int(viewer.decode())
            
            # Skip blocked users
            if viewer_id in all_blocked_users:
                continue
            
            if str(viewer_id) != str(user_id):
                overlap_counter[str(viewer_id)] += 1

    similar_users = {
        u: c for u, c in overlap_counter.items()
        if c >= MIN_OVERLAP
    }

    if not similar_users:
        return "no_similar_users"

    top_users = sorted(
        similar_users.items(),
        key=lambda x: x[1],
        reverse=True
    )[:MAX_SIMILAR_USERS]

    # ---------------------------
    # SCORE MEDIA (Collaborative)
    # ---------------------------
    media_scores = defaultdict(float)

    for sim_user_id, overlap in top_users:
        sim_media = redis.zrangebyscore(
            f"user:viewed:{sim_user_id}",
            cutoff,
            now,
            withscores=True
        )

        for media_id, view_ts in sim_media:
            media_id = media_id.decode()

            if media_id in user_media_ids:
                continue

            decay = time_decay(view_ts, now)
            media_scores[media_id] += overlap * decay

    if not media_scores:
        return "no_media_scored"


    # ---------------------------
    #  ADD THIS: GET PENALTY DATA
    # ---------------------------
    
    # Get all penalty tracking data
    creator_penalties = redis.zrange(
        f"user:creator_penalty:{user_id}", 0, -1, withscores=True
    )
    category_penalties = redis.zrange(
        f"user:category_penalty:{user_id}", 0, -1, withscores=True
    )
    hashtag_penalties = redis.zrange(
        f"user:hashtag_penalty:{user_id}", 0, -1, withscores=True
    )
    similar_ni_media = set(
        mid.decode() for mid in redis.zrange(f"user:similar_ni:{user_id}", 0, -1)
    )
    
    # Convert to dicts for fast lookup
    creator_penalty_map = {cid.decode(): count for cid, count in creator_penalties}
    category_penalty_map = {cat.decode(): count for cat, count in category_penalties}
    hashtag_penalty_map = {tag.decode(): count for tag, count in hashtag_penalties}
    
    # ---------------------------
    #  ADD THIS: APPLY PENALTIES
    # ---------------------------
    
    # Fetch media metadata in bulk
    from .models import Media
    
    scored_media_ids = list(media_scores.keys())
    media_data = Media.objects.filter(id__in=scored_media_ids).values(
        'id', 'user_id', 'category'
    )
    
    penalties_applied = 0
    
    for media_obj in media_data:
        media_id = str(media_obj['id'])
        creator_id = str(media_obj['user_id'])
        category = media_obj.get('category')
        
        if media_id not in media_scores:
            continue
        
        original_score = media_scores[media_id]
        penalty_multiplier = 1.0
        
        # 1. Creator penalty (80% reduction)
        if creator_id in creator_penalty_map:
            penalty_count = creator_penalty_map[creator_id]
            # Graduated: 1 strike = 0.2, 2 strikes = 0.04, 3+ strikes = 0.008
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            penalty_multiplier *= creator_penalty
        
        # 2. Category penalty (50% reduction)
        if category and category in category_penalty_map:
            penalty_count = category_penalty_map[category]
            # Graduated: 1 strike = 0.5, 2 strikes = 0.35, 3+ strikes = 0.25
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
        
        # 3. Similar media penalty (60% reduction)
        if media_id in similar_ni_media:
            penalty_multiplier *= PENALTY_SIMILAR_MEDIA
        
        # Apply combined penalty
        if penalty_multiplier < 1.0:
            media_scores[media_id] *= penalty_multiplier
            penalties_applied += 1
            
            logger.debug(
                f"Applied {(1-penalty_multiplier)*100:.0f}% penalty to media {media_id} "
                f"(creator: {creator_id}, original: {original_score:.2f}, "
                f"new: {media_scores[media_id]:.2f})"
            )
    
    # ---------------------------
    #  ADD THIS: REMOVE VERY LOW SCORES
    # ---------------------------
    
    # Remove items with score < 5% of max (too heavily penalized)
    if media_scores:
        max_score = max(media_scores.values())
        threshold = max_score * 0.05
        
        before_count = len(media_scores)
        media_scores = {
            mid: score for mid, score in media_scores.items() 
            if score >= threshold
        }
        removed = before_count - len(media_scores)
        
        if removed > 0:
            logger.info(f"Removed {removed} heavily penalized items for user {user_id}")


    # ---------------------------
    # FILTER BLOCKED USERS' MEDIA (NEW)
    # ---------------------------
    if all_blocked_users:
        from .models import Media
        
        scored_media_ids = list(media_scores.keys())
        
        # Get which scored media are from blocked users
        blocked_media = Media.objects.filter(
            id__in=scored_media_ids,
            user_id__in=all_blocked_users
        ).values_list('id', flat=True)
        
        # Remove blocked users' media
        for blocked_id in blocked_media:
            if str(blocked_id) in media_scores:
                del media_scores[str(blocked_id)]
        
        if not media_scores:
            return "all_filtered_by_blocks"

    # ---------------------------
    # APPLY NOT INTERESTED PENALTIES
    # ---------------------------
    ni_media_key = f"user:ni:media:{user_id}"
    ni_creator_key = f"user:ni:creator:{user_id}"

    not_interested_media = {
        mid.decode() for mid in redis.smembers(ni_media_key)
    }
    not_interested_creators = {
        cid.decode() for cid in redis.smembers(ni_creator_key)
    }

    # Remove explicitly disliked media
    for media_id in list(media_scores.keys()):
        if media_id in not_interested_media:
            del media_scores[media_id]

    if not media_scores:
        return "all_filtered_by_not_interested"

    """
    # Penalize creators
    fallback_needed = []

    for media_id in list(media_scores.keys()):
        creator_id = redis.get(f"media:creator:{media_id}")

        if creator_id:
            creator_id = creator_id.decode()

            if creator_id in not_interested_creators:
                media_scores[media_id] *= 0.1

        else:
            fallback_needed.append(media_id)

    # ---------------------------
    # FALLBACK TO DB
    # ---------------------------
    if fallback_needed:
        from .models import Media

        db_media = Media.objects.filter(
            id__in=fallback_needed
        ).values("id", "user_id")

        for obj in db_media:
            media_id = str(obj["id"])
            creator_id = str(obj["user_id"])

            redis.set(f"media:creator:{media_id}", creator_id)

            if creator_id in not_interested_creators:
                media_scores[media_id] *= 0.1
    """

    # ---------------------------
    # BLEND TRENDING
    # ---------------------------
    for media_id in list(media_scores.keys()):
        trending_score = redis.zscore(TRENDING_ZSET_KEY, media_id) or 0
        media_scores[media_id] = (
            media_scores[media_id] * COLLAB_WEIGHT
            + trending_score * TRENDING_WEIGHT
        )

    # ---------------------------
    # SAVE RECOMMENDATIONS
    # ---------------------------
    if media_scores:
        redis.zadd(reco_key, media_scores)
        redis.zremrangebyrank(reco_key, 0, -MAX_RECO_ITEMS - 1)

    return f"ok:{len(media_scores)}"



@shared_task()
def dispatch_recommendation_tasks():
    redis = get_redis_connection("default")
    now = int(time.time())
    cutoff = now - WINDOW_SECONDS

    active_users = redis.zrangebyscore(
        "active:users",
        cutoff,
        now
    )

    for user_id in active_users:
        #build_user_recommendations.delay(user_id.decode())
        build_user_recommendations_WITH_BLOCK_FILTER.delay(user_id.decode())

    return f"dispatched:{len(active_users)}"


#_________________________________
#
#new task to setup for displaying similar media to users with similar iterest
#making the platform stronger and more attractive to the users providing similar
#interest based media to users
#________________________________


#---------------------------------------------------------------------------
#
#modification after refractoring the following media function with Class
#---------------------------------------------------------------------------


@shared_task
def sync_not_interested_to_redis():
    """ENHANCED: Now syncs hashtag penalties too"""
    from .models import UserHashtagPreference, Media
    
    redis = get_redis_connection("default")
    synced_users = 0
    synced_media = 0
    synced_hashtags = 0
    
    try:
        prefs = UserHashtagPreference.objects.exclude(
            not_interested_media=[]
        ).select_related('user')
        
        for pref in prefs:
            user_id = pref.user_id
            media_ids = pref.not_interested_media or []
            
            if media_ids:
                # Sync media
                ni_media_key = f"user:ni:media:{user_id}"
                redis.delete(ni_media_key)
                redis.sadd(ni_media_key, *media_ids)
                synced_media += len(media_ids)
                
                # Sync creators
                media_creators = Media.objects.filter(
                    id__in=media_ids
                ).values_list('user_id', flat=True).distinct()
                
                if media_creators:
                    ni_creator_key = f"user:ni:creator:{user_id}"
                    redis.delete(ni_creator_key)
                    redis.sadd(ni_creator_key, *media_creators)
            
            # ✅ NEW: Sync hashtag penalties
            not_interested_hashtags = pref.not_interested_hashtags or []
            if not_interested_hashtags:
                hashtag_penalty_key = f"user:hashtag_penalty:{user_id}"
                redis.delete(hashtag_penalty_key)
                hashtag_dict = {str(tag): 1.0 for tag in not_interested_hashtags}
                redis.zadd(hashtag_penalty_key, hashtag_dict)
                redis.expire(hashtag_penalty_key, 60 * 60 * 24 * 30)
                synced_hashtags += len(not_interested_hashtags)
            
            synced_users += 1
        
        logger.info(f"Synced {synced_users} users, {synced_media} media, {synced_hashtags} hashtags")
        return f"success:{synced_users}_users,{synced_media}_media,{synced_hashtags}_hashtags"
        
    except Exception as e:
        logger.exception(f"Error syncing: {e}")
        return f"error:{str(e)}"



@shared_task
def rebuild_penalties_from_not_interested():
    """
    Rebuild creator/category penalties from existing not_interested_media
    Runs daily to maintain penalties even after Redis expiry
    """
    from .models import UserHashtagPreference, Media
    from collections import Counter
    
    redis = get_redis_connection("default")
    rebuilt_users = 0
    rebuilt_creators = 0
    rebuilt_categories = 0
    
    try:
        prefs = UserHashtagPreference.objects.exclude(
            not_interested_media=[]
        ).select_related('user')
        
        for pref in prefs:
            user_id = pref.user_id
            media_ids = pref.not_interested_media or []
            
            if not media_ids:
                continue
            
            # Fetch media creators and categories
            media_data = Media.objects.filter(
                id__in=media_ids
            ).values('id', 'user_id', 'category')
            
            # Count appearances
            creator_counter = Counter()
            category_counter = Counter()
            
            for media in media_data:
                creator_counter[media['user_id']] += 1
                if media.get('category'):
                    category_counter[media['category']] += 1
            
            # Rebuild creator penalties
            if creator_counter:
                creator_penalty_key = f"user:creator_penalty:{user_id}"
                redis.delete(creator_penalty_key)
                penalty_dict = {str(cid): float(count) for cid, count in creator_counter.items()}
                redis.zadd(creator_penalty_key, penalty_dict)
                redis.expire(creator_penalty_key, 60 * 60 * 24 * 90)
                rebuilt_creators += len(creator_counter)
            
            # Rebuild category penalties
            if category_counter:
                category_penalty_key = f"user:category_penalty:{user_id}"
                redis.delete(category_penalty_key)
                penalty_dict = {str(cat): float(count) for cat, count in category_counter.items()}
                redis.zadd(category_penalty_key, penalty_dict)
                redis.expire(category_penalty_key, 60 * 60 * 24 * 60)
                rebuilt_categories += len(category_counter)
            
            rebuilt_users += 1
        
        logger.info(f"Rebuilt penalties: {rebuilt_users} users, {rebuilt_creators} creators, {rebuilt_categories} categories")
        return f"success:{rebuilt_users}_users,{rebuilt_creators}_creators,{rebuilt_categories}_categories"
        
    except Exception as e:
        logger.exception(f"Error rebuilding: {e}")
        return f"error:{str(e)}"



@shared_task
def populate_creator_mappings():
    """
    Pre-populate media:creator:{media_id} mappings in Redis.
    
    This caches the creator_id for each media so build_user_recommendations
    doesn't have to query the database.
    
    Run this:
    - Once as initial setup
    - Periodically (every 24 hours) for new media
    - After bulk media imports
    """
    from .models import Media
    
    redis = get_redis_connection("default")
    
    try:
        # Get recent media (last 30 days)
        cutoff = timezone.now() - timedelta(days=30)
        recent_media = Media.objects.filter(
            created_at__gte=cutoff
        ).values('id', 'user_id')
        
        # Batch populate using pipeline for efficiency
        pipe = redis.pipeline()
        count = 0
        
        for media in recent_media:
            pipe.set(f"media:creator:{media['id']}", media['user_id'])
            count += 1
            
            # Execute in batches of 1000
            if count % 1000 == 0:
                pipe.execute()
                pipe = redis.pipeline()
        
        # Execute remaining
        if count % 1000 != 0:
            pipe.execute()
        
        logger.info(f"Populated {count} creator mappings")
        return f"success:{count}_mappings"
        
    except Exception as e:
        logger.exception(f"Error populating creator mappings: {e}")
        return f"error:{str(e)}"


@shared_task
def cleanup_stale_redis_data():
    """
    Clean up old Redis data to prevent memory bloat.
    
    Run this:
    - Once per day
    - During low-traffic hours
    """
    redis = get_redis_connection("default")
    
    try:
        cleaned = {
            'seen_feeds': 0,
            'view_tracking': 0,
            'creator_mappings': 0
        }
        
        # 1. Clean old seen feeds (> 60 days)
        pattern = "user:seen_feed:*"
        for key in redis.scan_iter(pattern, count=100):
            ttl = redis.ttl(key)
            if ttl == -1:  # No expiry set
                redis.expire(key, 60 * 60 * 24 * 30)  # Set 30 days
                cleaned['seen_feeds'] += 1
        
        # 2. Clean old view tracking (> 30 days)
        cutoff = int((timezone.now() - timedelta(days=30)).timestamp())
        
        for pattern in ["user:viewed:*", "media:viewed_by:*"]:
            for key in redis.scan_iter(pattern, count=100):
                # Remove old entries
                removed = redis.zremrangebyscore(key, 0, cutoff)
                if removed > 0:
                    cleaned['view_tracking'] += removed
        
        logger.info(f"Cleanup: {cleaned}")
        return f"success:{cleaned}"
        
    except Exception as e:
        logger.exception(f"Error during cleanup: {e}")
        return f"error:{str(e)}"


#---------------------------------------------------------------------------
#
#
#---------------------------------------------------------------------------






