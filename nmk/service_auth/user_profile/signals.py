import logging
from django.db.models.signals import post_save
from django.db.models.signals import post_delete

from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Story, Media

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