# signals.py

from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import UserUpload, CustomGroupAdmin

from django.db.models.signals import pre_save

from allauth.account.signals import user_logged_in
from django.contrib import messages
from django.core.cache import cache

@receiver(pre_save, sender=UserUpload)
def delete_old_file_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    old_file = old_instance.file
    new_file = instance.file

    if old_file and old_file.name and old_file != new_file:
        try:
            storage = old_file.storage
            if storage.exists(old_file.name):
                storage.delete(old_file.name)
                print(f"Deleted old file from R2: {old_file.name}")
        except Exception as e:
            print(f"Error deleting old file: {e}")
'''
@receiver(post_delete, sender=UserUpload)
def delete_user_upload_file_on_delete(sender, instance, **kwargs):
    # Delete main file from bucket
    if instance.file:
        try:
            instance.file.delete(save=False)
            print("Deleted uploaded file from bucket")
        except Exception as e:
            print(f"Error deleting uploaded file: {e}")

    # Optional: Delete any thumbnails or other related files if you store them separately
    if hasattr(instance, 'thumbnail') and instance.thumbnail:
        try:
            instance.thumbnail.delete(save=False)
            print("Deleted thumbnail from bucket")
        except Exception as e:
            print(f"Error deleting thumbnail: {e}")
'''

#google one click login setup
@receiver(user_logged_in)
def handle_social_login_cookies(request, user, **kwargs):
    """
    Listens for successful Allauth sign-ins to seamlessly set 
    the 14-day session expiry, cache profiles, and set frontend cookies.
    """
    # 1. Only process if the login originated from a social account (Google)
    if hasattr(user, 'socialaccount_set') and user.socialaccount_set.exists():
        
        # 2. Replicate your exact "Remember Me" session duration logic (14 days)
        request.session.set_expiry(60 * 60 * 24 * 14)  
        
        # 3. Synchronize your custom server-side caching profile layer
        # cache.set(f'user_{user.id}', user.username)

        # 4. Inject a custom attribute onto the request so our view middleware 
        # knows to attach the 'username' cookie to the final HTTP redirect object
        request._attach_custom_google_cookies = True

