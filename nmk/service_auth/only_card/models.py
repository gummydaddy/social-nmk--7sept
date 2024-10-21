from xml.dom import ValidationErr
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.db import models
import os
import uuid
from django.dispatch import receiver
from django.utils import timezone
from django_countries.fields import CountryField
import random
import string
from django.core.mail import send_mail
from cryptography.fernet import Fernet
from django.conf import settings
from .user_fields import LockedField
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def default_file_name():
    return timezone.now().strftime('%Y%m%d%H%M%S')
    # Add your custom fields here

#profile picture16april

#document upload & delete15april


class TemporaryUser(models.Model):
    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # This should be hashed for security
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    token = models.CharField(max_length=100, unique=True)
    token_expires = models.DateTimeField()

    def is_token_valid(self):
        return self.token_expires > timezone.now()


class UserStorage(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    total_storage_used = models.BigIntegerField(default=0)  # Store in bytes

    def __str__(self):
        return f"{self.user.username} - {self.total_storage_used / (1024 * 1024)} MB"


class UserUpload(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=50)
    file_name = models.CharField(max_length=255)
    upload_date = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='uploads/')
    country = CountryField()
    encryption_key = models.CharField(max_length=44, blank=True, null=True)

    def save(self, *args, **kwargs):
        file_size = self.file.size  # Get the size of the uploaded file

        # Check the user's storage usage
        user_storage, created = UserStorage.objects.get_or_create(user=self.user)
        if user_storage.total_storage_used + file_size > 512 * 1024 * 1024:  # 512 MB limit
            raise ValueError("Storage limit exceeded")

        if not self.encryption_key:
            self.encryption_key = Fernet.generate_key().decode('utf-8')

        super().save(*args, **kwargs)

        # Encrypt the file after saving
        fernet = Fernet(self.encryption_key.encode('utf-8'))
        file_path = self.file.path
        with open(file_path, 'rb') as file:
            original_file_data = file.read()
        encrypted_file_data = fernet.encrypt(original_file_data)

        # Save the encrypted file
        with open(file_path, 'wb') as encrypted_file:
            encrypted_file.write(encrypted_file_data)

        # Update user's total storage
        user_storage.total_storage_used += file_size
        user_storage.save()

    def delete_file(self):
        if self.file:
            try:
                file_path = self.file.path
                file_size = self.file.size
                if os.path.exists(file_path):
                    os.remove(file_path)

                # Update user's storage after file deletion
                user_storage = UserStorage.objects.get(user=self.user)
                user_storage.total_storage_used -= file_size
                user_storage.save()
            except UserStorage.DoesNotExist:
                logger.error("User storage not found.")
            except Exception as e:
                logger.error(f"Error deleting file: {e}")

# class TemporarilyLock(models.Model):
#     user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)
#     locked_by = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='locked_users')
#     locked_at = models.DateTimeField(auto_now_add=True)
#     expires_at = models.DateTimeField(null=True, blank=True)

#     def is_expired(self):
#         return self.expires_at and self.expires_at < timezone.now()


#Criteria for Service Provider Registration:Model18april
class RegistrationForm(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE)
    criteria = models.CharField(max_length=100)  # Define criteria field
    legal_documents = models.FileField(upload_to='legal_documents/', null=True, blank=True)
    gst_number = models.CharField(max_length=15)  # Add GST number field
    association_name = models.CharField(max_length=100, null=True, blank= True)  # Add association name field
    subgroup = models.ForeignKey('CustomGroup', on_delete=models.CASCADE, null=True, blank=True)
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')


    def __str__(self):
        return self.user.username + ' - Application'
        

#image upload27april create a new app and move 27april to the and connet it to this app



#notion27april


#send recive from service provider 
class File(models.Model):
    # Define fields for the File model
    name = models.CharField(max_length=255)
    upload = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


#create card24april   
class Card(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='card', null=True)
    card_number = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    card_image = models.ImageField(upload_to='card_images/', null=True, blank=True)

    def __str__(self):
        return f"Card for {self.user.username}"
    


#kyc25april
class KYC(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, null=True, blank=True)
    uploaded_image = models.ImageField(upload_to='kyc_images/', null=True)
    #kyc_video = models.FileField(upload_to='kyc_videos/', null=True)
    phone_number = models.CharField(max_length=15)

    def __str__(self):
        return f"KYC information for {self.user.username if self.user else 'Anonymous'}"


#group29april           
class CustomGroup(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    parent_group = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subgroups')
    users = models.ManyToManyField(AuthUser, blank=True, related_name='custom_groups')
    is_approved = models.BooleanField(default=False)
    legal_documents_Association = models.FileField(upload_to='legal_documents_Association/', null=True, blank=True)
    admins = models.ManyToManyField(AuthUser, blank=True, related_name='admin_groups')
    pending_approval = models.CharField(max_length=10, choices=[('approve', 'Approve'), ('deny', 'Deny'), ('pending', 'Pending')], default='pending')
    registration_form = models.ForeignKey(RegistrationForm, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name


class CustomGroupAdmin(models.Model):
    group = models.ForeignKey(CustomGroup, on_delete=models.CASCADE, related_name='group_admins')
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} - {self.group.name}"

    def clean(self):
        if self.group.parent_group is None and not self.user.is_superuser:
            raise ValidationErr('Only superusers can be admins for main groups.')


class UserAssociation(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)
    subgroup = models.ForeignKey('CustomGroup', on_delete=models.CASCADE, null=True, blank=True)
    association_name = models.CharField(max_length=100)
    association_email = models.EmailField()
    # Add a field to track approval status
    is_approved = models.BooleanField(default=False)






    # class CustomGroup(models.Model):
    # name = models.CharField(max_length=100)
    # description = models.TextField(blank=True, null=True)
    # parent_group = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subgroups')
    # users = models.ManyToManyField(AuthUser, blank=True, related_name='custom_groups')
    # admins = models.ManyToManyField(AuthUser, blank=True, related_name='admin_groups')
    # is_approved = models.BooleanField(default=False)
    # legal_documents = models.FileField(upload_to='legal_documents/', null=True, blank=True)
    # pending_approval = models.BooleanField(default=True)  # Simplified for status management

    # def __str__(self):
    #     return self.name
    

    # class CustomGroupAdmin(models.Model):
    # group = models.ForeignKey(CustomGroup, on_delete=models.CASCADE, related_name='group_admins')
    # user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)

    # def __str__(self):
    #     return f"{self.user.username} - {self.group.name}"

    # def clean(self):
    #     if self.group.parent_group is None and not self.user.is_superuser:
    #         raise ValidationErr('Only superusers can be admins for main groups.')
        


    # class RegistrationForm(models.Model):
    # user = models.OneToOneField(AuthUser, on_delete=models.CASCADE)
    # association_name = models.CharField(max_length=100)  
    # gst_number = models.CharField(max_length=15)  
    # country_of_origin = models.CharField(max_length=100)  
    # legal_documents = models.FileField(upload_to='legal_documents/', null=True, blank=True)
    # status = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')

    # def __str__(self):
    #     return f"{self.user.username} - Registration"