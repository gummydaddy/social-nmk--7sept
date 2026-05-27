import os
import logging
from django.db.models.signals import post_save
from django.db.models.signals import post_delete, pre_save
from django.utils import timezone
from django.db import transaction

from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Story, Media

from service_auth.notion.models import Follow, Notification, Comment, Hashtag, BlockedUser

#from .tasks import enqueue_recompute_global_score # Celery task wrapper
from django.core.cache import cache

from django_redis import get_redis_connection

#from django.core.cache import cache

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        logger.info(f'Created profile for user {instance.username}')

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
    logger.info(f'Saved profile for user {instance.username}')

@receiver(post_delete, sender=Story)
def delete_media_with_story(sender, instance, **kwargs):
    if instance.media:
        try:
            # Delete the associated media file from storage
            instance.media.file.delete(save=False)

            # Delete the media instance
            instance.media.delete()
        except Exception as e:
            logger.error(f"Error deleting media for story {instance.id}: {e}")



# Delete old profile picture or cover photo when updated
@receiver(pre_save, sender=Profile)
def delete_old_profile_picture_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return  # New object, no need to delete old files

    try:
        old_instance = Profile.objects.get(pk=instance.pk)
    except Profile.DoesNotExist:
        return

    # Delete old profile picture if replaced
    if old_instance.profile_picture and old_instance.profile_picture != instance.profile_picture:
        try:
            old_instance.profile_picture.delete(save=False)
        except Exception as e:
            print(f"Error deleting old profile picture: {e}")

    # Delete old cover photo if replaced
    if old_instance.cover_photo and old_instance.cover_photo != instance.cover_photo:
        try:
            old_instance.cover_photo.delete(save=False)
        except Exception as e:
            print(f"Error deleting old cover photo: {e}")



# Delete profile picture and cover photo when profile is deleted
@receiver(post_delete, sender=Profile)
def delete_profile_media_on_delete(sender, instance, **kwargs):
    for field in ['profile_picture', 'cover_photo']:
        media_file = getattr(instance, field)
        if media_file:
            try:
                media_file.delete(save=False)
            except Exception as e:
                print(f"Error deleting {field}: {e}")



# Delete media file and its thumbnail when Media object is deleted
@receiver(post_delete, sender=Media)
def delete_media_file_on_delete(sender, instance, **kwargs):
    # Delete media file
    if instance.file:
        try:
            instance.file.delete(save=False)
            print("Deleted media file")
        except Exception as e:
            print(f"Error deleting media file: {e}")

    # Delete thumbnail
    if instance.thumbnail:
        try:
            instance.thumbnail.delete(save=False)
            print("Deleted thumbnail")
        except Exception as e:
            print(f"Error deleting thumbnail file: {e}")




"""
for future
# Delete old associated file if media is edited 
@receiver(pre_save, sender=Media)
def delete_old_file_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return  # New object

    try:
        old_instance = Media.objects.get(pk=instance.pk)
    except Media.DoesNotExist:
        return

    if old_instance.file and old_instance.file != instance.file:
        if os.path.exists(old_instance.file.path):
            try:
                os.remove(old_instance.file.path)
            except Exception as e:
                print(f"Error deleting old media file: {e}")
"""

#________________________________
#
#
#For media tracking using util updates and new tasks
#
#
#________________________________
'''
def _schedule_media_recompute(media_id):
    # Debounce/coalesce via Celery (task will handle throttling)
    enqueue_recompute_global_score.delay(media_id)


@receiver(post_save, sender=Media)
def media_changed(sender, instance, created, **kwargs):
    """
    Recompute global score whenever a Media object itself changes.
    """
    transaction.on_commit(lambda: _schedule_media_recompute(instance.id))


@receiver(m2m_changed, sender=Media.likes.through)
def likes_changed(sender, instance, action, **kwargs):
    """
    Recompute when likes are added/removed.
    """
    if action in ("post_add", "post_remove", "post_clear"):
        transaction.on_commit(lambda: _schedule_media_recompute(instance.id))
'''

#________________________________
#
#
#For media tracking using util updates and new tasks
#
#
#________________________________





# ------------------------------------------------------------------------------------ 
#global Media cache invalidation signals with util helper functions and view functions 
# ------------------------------------------------------------------------------------ 

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .utils import (
    GLOBAL_EXPLORE_CACHE_KEY,
    GLOBAL_EXPLORE_CACHE_TIMEOUT,
    GLOBAL_EXPLORE_CAP,
    build_and_cache_global_explore,
    get_global_explore_ids,
    get_media_qs_from_cached_ids,
    _serialize_media_for_cache,
    TRENDING_ZSET_KEY
)

@receiver([post_save, post_delete], sender=Media)
def invalidate_global_explore_cache(sender, instance, **kwargs):
    """
    When media is created/updated/deleted we should invalidate the global explore cache
    because the global "recent" set changed.
    """
    try:
        cache.delete(GLOBAL_EXPLORE_CACHE_KEY)
        logger.debug("Invalidated global explore cache due to Media change (id=%s)", getattr(instance, 'id', None))
    except Exception as e:
        logger.exception("Error invalidating global explore cache: %s", e)



def remove_from_trending(media_id):
    """Helper to remove media from Redis trending set."""
    try:
        redis_conn = get_redis_connection("default")
        redis_conn.zrem(TRENDING_ZSET_KEY, str(media_id))
    except Exception as e:
        print(f"Error removing media {media_id} from trending: {e}")


#  CASE 1 — Media becomes private
@receiver(pre_save, sender=Media)
def remove_if_becoming_private(sender, instance, **kwargs):
    if not instance.pk:
        return  # new object, ignore

    try:
        old_instance = Media.objects.get(pk=instance.pk)
    except Media.DoesNotExist:
        return

    # If was public before and now being set to private
    if old_instance.is_private is False and instance.is_private is True:
        remove_from_trending(instance.pk)


#  CASE 2 — Media deleted
@receiver(post_delete, sender=Media)
def remove_deleted_media_from_trending(sender, instance, **kwargs):
    remove_from_trending(instance.pk)



@receiver(post_save, sender=Media)
def cache_media_creator(sender, instance, created, **kwargs):
    """
    Automatically cache creator mapping when media is created.
    
    This ensures build_user_recommendations doesn't need DB lookups.
    """
    if created:
        try:
            redis_conn = get_redis_connection("default")
            redis_conn.set(f"media:creator:{instance.id}", instance.user_id)
            logger.debug(f"Cached creator for media {instance.id}")
        except Exception as e:
            logger.warning(f"Failed to cache creator for media {instance.id}: {e}")


# ------------------------------------------------------------------------------------
#global Media cache invalidation signals with util helper functions and view functions 
# ------------------------------------------------------------------------------------ 


# ------------------------------------------------------------------------------------ 
# for blocked user setup
# ------------------------------------------------------------------------------------

@receiver(post_save, sender=BlockedUser)
def on_user_blocked(sender, instance, created, **kwargs):
    """
    Automatically clean caches when user is blocked
    """
    if not created:
        return
    
    try:
        redis = get_redis_connection("default")
        
        # Clear blocker's caches
        redis.delete(f"user:seen_feed:{instance.blocker_id}")
        
        # Clear blocker's recommendations (will be rebuilt without blocked user)
        redis.delete(f"user:reco:{instance.blocker_id}")
        
        logger.info(f"Cleared caches for user {instance.blocker_id} after blocking {instance.blocked_id}")
        
    except Exception as e:
        logger.warning(f"Failed to clear caches on block: {e}")


@receiver(post_delete, sender=BlockedUser)
def on_user_unblocked(sender, instance, **kwargs):
    """
    Automatically clean caches when user is unblocked
    """
    try:
        redis = get_redis_connection("default")
        
        # Clear blocker's caches
        redis.delete(f"user:seen_feed:{instance.blocker_id}")
        redis.delete(f"user:reco:{instance.blocker_id}")
        
        logger.info(f"Cleared caches for user {instance.blocker_id} after unblocking {instance.blocked_id}")
        
    except Exception as e:
        logger.warning(f"Failed to clear caches on unblock: {e}")

# ------------------------------------------------------------------------------------ 
# for blocked user setup
# ------------------------------------------------------------------------------------ 
