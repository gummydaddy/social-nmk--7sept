#user_profile/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as AuthUser
from django.core.validators import MaxValueValidator, MinValueValidator
#from notion.models import Follow
from django.core.files.storage import FileSystemStorage
from .storage import CompressedMediaStorage
from django.utils import timezone
from django.db.models import JSONField
from django_countries.fields import CountryField
from django.utils import timezone
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import os
import subprocess
from moviepy.editor import VideoFileClip
from django.conf import settings


class Profile(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    saved_uploads = models.ManyToManyField('Media', related_name='saved_by_users', blank=True)
    is_private = models.BooleanField(default=False)  # New field to track privacy
    country = CountryField(blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True, help_text="Select the category that best describes your content.")
    email_confirmed = models.BooleanField(default=False)  # New field to track email confirmation
    firebase_uid = models.CharField(max_length=255, blank=True, null=True)  # Field to store Firebase UID

    def __str__(self):
        return self.user.username

#from .tasks import generate_thumbnail_task

class Media(models.Model):
    MEDIA_TYPES = (
        ('image', 'Image'),
        ('video', 'Video'),
    )
    
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='media/', storage=CompressedMediaStorage())
    description = models.TextField(blank=True, null=True)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES, null=True)
    hashtags = models.ManyToManyField('Hashtag', related_name='media', blank=True)
    category = models.CharField(max_length=50, blank=True, null=True, help_text="Category of the media.")
    is_paid = models.BooleanField(default=False)
    thumbnail = models.ImageField(upload_to="thumbnails/", blank=True, null=True)  # Add this field
    created_at = models.DateTimeField(auto_now_add=True)
    country = CountryField(blank=True, null=True)
    likes = models.ManyToManyField(AuthUser, related_name='liked_uploads', blank=True)
    view_count = models.PositiveIntegerField(default=0)  # To keep track of views
    reported_by = models.ManyToManyField(AuthUser, related_name='reported_media', blank=True)  #report
    report_count = models.IntegerField(default=0)
    tags = models.ManyToManyField(AuthUser, related_name='tagged_media', blank=True)  # New field for tagging users
    is_private = models.BooleanField(default=False)  # New field to track privacy
    is_story = models.BooleanField(default=False)  # New field to differentiate story media
    
    def __str__(self):
        return self.description if self.description else "Media"

    def delete_file(self):
        if self.file:
            self.file.delete(save=False)
    '''
    def save(self, *args, **kwargs):
        is_new = self.pk is None  # Check if it's a new object
        super().save(*args, **kwargs)
        if is_new:  # Run the Celery task only for new media
            generate_thumbnail_task.delay(self.id)
    '''
    def save(self, *args, **kwargs):
        if not self.thumbnail:  # Generate only if not already created
            self.generate_thumbnail()
        super().save(*args, **kwargs)

    def generate_thumbnail(self):
        """Generate a thumbnail for images or videos."""
        if self.file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            self.create_image_thumbnail()
       # elif self.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
       #     self.create_video_thumbnail()

    def create_image_thumbnail(self):
        """Generate a compressed thumbnail for images."""
        try:
            img = Image.open(self.file)
            img.thumbnail((250, 150))  # Resize to 150x150 pixels

            # Convert to JPEG if needed
            thumb_io = BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(thumb_io, format=img_format, quality=85)  # Adjust quality for compression

            # Save thumbnail
            thumb_name = f"thumb_{os.path.basename(self.file.name)}"
            self.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=False)
        except Exception as e:
            print(f"Error creating image thumbnail: {e}")
    '''
    def create_video_thumbnail(self):
        """Generate a thumbnail for videos without FFmpeg."""
        if not self.file:
            return  # Skip if file is missing

        video_path = self.file.path  # This ensures an absolute path
        if not os.path.exists(video_path):
            print(f"File not found: {video_path}")
            return  # Prevent errors

        try:
            clip = VideoFileClip(video_path)
            frame = clip.get_frame(1)  # Capture a frame at 1 second

            # Save frame as thumbnail
            thumb_name = f"thumb_{os.path.splitext(os.path.basename(self.file.name))[0]}.jpg"
            thumb_path = os.path.join(settings.MEDIA_ROOT, "thumbnails", thumb_name)

            from PIL import Image
            import numpy as np

            img = Image.fromarray(np.uint8(frame))
            img.thumbnail((250, 150))
            img.save(thumb_path, format="JPEG", quality=85)

            # Save to model field
            self.thumbnail.name = os.path.relpath(thumb_path, settings.MEDIA_ROOT)
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")
    '''

class Audio(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='audio')
    file = models.FileField(upload_to='media/', storage=CompressedMediaStorage())
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True, help_text="Category of the audio.")
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    country = CountryField(blank=True, null=True)
    likes = models.ManyToManyField(AuthUser, related_name='liked_audio', blank=True)
    view_count = models.PositiveIntegerField(default=0)  # To keep track of views
    reported_by = models.ManyToManyField(AuthUser, related_name='reported_audio', blank=True)  # report
    report_count = models.IntegerField(default=0)
    tags = models.ManyToManyField(AuthUser, related_name='tagged_audio', blank=True)  # New field for tagging users
    is_private = models.BooleanField(default=False)  # New field to track privacy
    duration = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(3600)], blank =True, null=True)  # in seconds
    size = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(1024*1024*100)])  # in bytes, max 100MB
    hashtags = models.ManyToManyField('Hashtag', related_name='audio', blank=True)

    def __str__(self):
        return self.description

    def delete_file(self):
        if self.file:
            self.file.delete(save=False)




class Story(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='stories')
    # media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='stories')
    media = models.OneToOneField(Media, on_delete=models.CASCADE)  # Ensure cascade delete
    created_at = models.DateTimeField(auto_now_add=True)
    viewers = models.ManyToManyField(AuthUser, related_name='viewed_stories', blank=True)
    
    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(hours=24)
    

            

class Hashtag(models.Model):
    name = models.CharField(max_length=25, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

class UserHashtagPreference(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='hashtag_preference')
    liked_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags liked by the user
    not_interested_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags marked as not interested by the user
    viewed_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags viewed by the user
    viewed_media = models.JSONField(default=list)  # Store the last viewed media IDs
    not_interested_media = models.JSONField(default=list)  # Store the last 50 unique media IDs that the user is not interested in
    
    #new catogery
    liked_categories = models.JSONField(default=list)  # Store the last 10 categories engaged with

    # New field to store the last 35 unique search keywords
    search_hashtags = models.JSONField(default=list)

    def add_viewed_hashtag(self, hashtags):
        self.viewed_hashtags = hashtags + self.viewed_hashtags
        self.viewed_hashtags = list(dict.fromkeys(self.viewed_hashtags))[:50]
        self.save(update_fields=['viewed_hashtags'])

    def add_viewed_media(self, media_ids):
        self.viewed_media = media_ids + self.viewed_media
        self.viewed_media = list(dict.fromkeys(self.viewed_media))[:50]
        self.save(update_fields=['viewed_media'])

    def add_not_interested_media(self, media_id):
        self.not_interested_media = [media_id] + self.not_interested_media
        self.not_interested_media = list(dict.fromkeys(self.not_interested_media))[:50]
        self.save(update_fields=['not_interested_media'])
    
    # New method to add search keywords to the add_liked_category list
    def add_liked_category(self, category):
        if category:  # Check if category is valid
            self.liked_categories = [category] + self.liked_categories
            self.liked_categories = list(dict.fromkeys(self.liked_categories))[:10]
            self.save(update_fields=['liked_categories'])

    # New method to add search keywords to the search_hashtags list
    def add_search_hashtag(self, search_keyword):
        """
        Add a search keyword to the search_hashtags list while ensuring it contains only unique
        keywords and stores only the last 35 entries (FIFO).
        """
        if search_keyword:  # Check if the search keyword is not empty
            self.search_hashtags = [search_keyword] + self.search_hashtags
            self.search_hashtags = list(dict.fromkeys(self.search_hashtags))[:35]
            self.save(update_fields=['search_hashtags'])



class AdminNotification(models.Model):
    media = models.ForeignKey(Media, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)


class Engagement(models.Model):
    ENGAGEMENT_TYPES = (
        ('view', 'View'),
        ('like', 'Like'),
        ('comment', 'Comment'),
    )

    media = models.ForeignKey(Media, on_delete=models.CASCADE)
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)
    engagement_type = models.CharField(max_length=50, choices=ENGAGEMENT_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['media', 'user', 'engagement_type'],
                condition=models.Q(engagement_type='view'),
                name='unique_view'
            )
        ]

    def __str__(self):
        return f'{self.user.username} {self.engagement_type} {self.media}'


class Buddy(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='buddy_list')
    buddy = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='buddies')
    
    class Meta:
        unique_together = ('user', 'buddy')

    def __str__(self):
        return f"{self.user.username}'s buddy: {self.buddy.username}"
    

# class Interaction(models.Model):
#     media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='interactions')
#     user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)
#     timestamp = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['-timestamp']
#         constraints = [
#             models.UniqueConstraint(fields=['media', 'user'], name='unique_interaction')
        # ]
