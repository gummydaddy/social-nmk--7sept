from django.utils.timezone import now
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import LoggedInUser
from django.contrib.auth.models import User as AuthUser
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from .models import UserEncryptionKeys, Message

from .encryption_utils import generate_key_pair, serialize_key

import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AuthUser)
def create_user_encryption_keys(sender, instance, created, **kwargs):
    if created:
        try:
            encryption_private, encryption_public = generate_key_pair()
            signing_private, signing_public = generate_key_pair()
            UserEncryptionKeys.objects.create(
                user=instance,
                encryption_public_key=serialize_key(encryption_public),
                encryption_private_key=serialize_key(encryption_private, is_private=True),
                signing_public_key=serialize_key(signing_public),
                signing_private_key=serialize_key(signing_private, is_private=True)
            )
            logger.info(f"Encryption keys created for user {instance.username}")
        except Exception as e:
            logger.error(f"Error creating encryption keys for user {instance.username}: {str(e)}")


'''
@receiver(user_logged_in)
def on_user_login(sender, **kwargs):
    LoggedInUser.objects.get_or_create(user=kwargs.get('user'))

@receiver(user_logged_out)
def on_user_logout(sender, **kwargs):
    LoggedInUser.objects.filter(user=kwargs.get('user')).delete()


'''

@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    # Just ensure the row exists, don't overwrite other sessions
    obj, created = LoggedInUser.objects.get_or_create(user=user)
    obj.last_activity = now()
    obj.save()

@receiver(user_logged_out)
def on_user_logout(sender, request, user, **kwargs):
    # Do NOT delete the row, otherwise other active sessions die
    try:
        obj = LoggedInUser.objects.get(user=user)
        obj.last_activity = now()  # mark as "inactive" or "logged out from this session"
        obj.save(update_fields=["last_activity"])
    except LoggedInUser.DoesNotExist:
        pass



# --- SIGNAL: Delete file from filesystem when Message object is deleted ---
'''
@receiver(post_delete, sender=Message)
def delete_message_file(sender, instance, **kwargs):
    """
    Deletes the file from the filesystem when the Message object is deleted.
    """
    if instance.file:
        try:
            instance.file.delete(save=False)
            logger.info(f"Deleted file for message {instance.id}")
        except Exception as e:
            logger.error(f"Error deleting file for message {instance.id}: {e}")

'''



# =========================================================
# DELETE MAIN MESSAGE FILE
# =========================================================
@receiver(post_delete, sender=Message)
def delete_message_files(sender, instance, **kwargs):
    """
    Delete uploaded file from storage
    when message is deleted.
    Works with:
    - S3
    - R2
    - DigitalOcean Spaces
    - local storage
    """

    try:

        if instance.file:

            try:

                file_name = instance.file.name

                # Delete from storage bucket
                instance.file.delete(save=False)

                logger.info(
                    f"✅ Deleted file from storage: "
                    f"{file_name}"
                )

            except Exception as e:

                logger.error(
                    f"Error deleting message file: {e}",
                    exc_info=True
                )

        logger.info(
            f"✅ Message cleanup completed "
            f"for message {instance.id}"
        )

    except Exception as e:

        logger.error(
            f"Message cleanup failed: {e}",
            exc_info=True
        )
