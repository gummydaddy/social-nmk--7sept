from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import LoggedInUser
from django.contrib.auth.models import User as AuthUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from .models import UserEncryptionKeys
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



@receiver(user_logged_in)
def on_user_login(sender, **kwargs):
    LoggedInUser.objects.get_or_create(user=kwargs.get('user'))

@receiver(user_logged_out)
def on_user_logout(sender, **kwargs):
    LoggedInUser.objects.filter(user=kwargs.get('user')).delete()
