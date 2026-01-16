import os
import logging
from django.db.models.signals import post_save
from django.db.models.signals import post_delete, pre_save
from django.utils import timezone
from django.db import transaction

from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Story, Media
#from .tasks import enqueue_recompute_global_score # Celery task wrapper
from django.core.cache import cache



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
'''
#new
@receiver(post_save, sender=Media)
def invalidate_global_explore_on_create(sender, instance, created, **kwargs):
    """
    When media is created/updated/deleted we should invalidate the global explore cache
    because the global "recent" set changed.
    """
    if created:
        try:
            cache.delete(GLOBAL_EXPLORE_CACHE_KEY)
            logger.debug("Invalidated global explore cache due to Media change (id=%s)", getattr(instance, 'id', None))
        except Exception as e:
            logger.exception("Error invalidating global explore cache: %s", e)

        #cache.delete(GLOBAL_EXPLORE_CACHE_KEY)

@receiver(post_delete, sender=Media)
def invalidate_global_explore_on_delete(sender, instance, **kwargs):
    cache.delete(GLOBAL_EXPLORE_CACHE_KEY)
'''

# ------------------------------------------------------------------------------------
#global Media cache invalidation signals with util helper functions and view functions 
# ------------------------------------------------------------------------------------ 
