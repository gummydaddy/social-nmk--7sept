import os
import logging
from django.db.models.signals import post_save
from django.db.models.signals import post_delete, pre_save

from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Story, Media

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

'''
@receiver([post_save, post_delete], sender=Media)
def invalidate_user_feed(sender, instance, **kwargs):
    user_id = instance.user.id
    pattern = f"user_feed_v1:{user_id}:page:*"
    from django_redis import get_redis_connection
    con = get_redis_connection("default")
    for key in con.scan_iter(pattern):
        con.delete(key)
'''



# Delete old profile picture if updated
@receiver(pre_save, sender=Profile)
def delete_old_profile_picture_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return  # New object, no need to delete

    try:
        old_instance = Profile.objects.get(pk=instance.pk)
    except Profile.DoesNotExist:
        return

    # Profile picture update
    if old_instance.profile_picture and old_instance.profile_picture != instance.profile_picture:
        if os.path.isfile(old_instance.profile_picture.path):
            try:
                os.remove(old_instance.profile_picture.path)
            except Exception as e:
                print(f"Error deleting old profile picture: {e}")

    # Cover photo update
    if old_instance.cover_photo and old_instance.cover_photo != instance.cover_photo:
        if os.path.isfile(old_instance.cover_photo.path):
            try:
                os.remove(old_instance.cover_photo.path)
            except Exception as e:
                print(f"Error deleting old cover photo: {e}")


# Delete profile & cover photo files when profile is deleted
@receiver(post_delete, sender=Profile)
def delete_profile_media_on_delete(sender, instance, **kwargs):
    for field in ['profile_picture', 'cover_photo']:
        media_file = getattr(instance, field)
        if media_file and hasattr(media_file, 'path') and os.path.isfile(media_file.path):
            try:
                os.remove(media_file.path)
            except Exception as e:
                print(f"Error deleting {field}: {e}")

'''
# Delete associated file if media is deleted in frontend do not delets the thumbnails 
@receiver(post_delete, sender=Media)
def delete_media_file_on_delete(sender, instance, **kwargs):
    """
    Deletes the media file from storage when the Media object is deleted.
    """
    if instance.file and hasattr(instance.file, 'path'):
        try:
            if os.path.exists(instance.file.path):
                os.remove(instance.file.path)
                print(f"Deleted media file: {instance.file.path}")
        except Exception as e:
            print(f"Error deleting media file {instance.file.path}: {e}")
'''

# Delete associated file if media is deleted in frontend also delets the related thumbnails 
@receiver(post_delete, sender=Media)
def delete_media_file_on_delete(sender, instance, **kwargs):
    """
    Deletes the media file and its associated thumbnail from storage when the Media object is deleted.
    """
    # 1. Delete main media file
    if instance.file and hasattr(instance.file, 'path'):
        try:
            if os.path.exists(instance.file.path):
                os.remove(instance.file.path)
                print(f"Deleted media file: {instance.file.path}")
        except Exception as e:
            print(f"Error deleting media file {instance.file.path}: {e}")

    # 2. Delete thumbnail file
    if instance.thumbnail and hasattr(instance.thumbnail, 'path'):
        try:
            if os.path.exists(instance.thumbnail.path):
                os.remove(instance.thumbnail.path)
                print(f"Deleted thumbnail: {instance.thumbnail.path}")
        except Exception as e:
            print(f"Error deleting thumbnail file {instance.thumbnail.path}: {e}")




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
