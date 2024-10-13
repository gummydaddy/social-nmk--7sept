#user_profile/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User as AuthUser
#from notion.models import Follow
from django.core.files.storage import FileSystemStorage
from .storage import CompressedMediaStorage
from django.utils import timezone
from django.db.models import JSONField



class Profile(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    saved_uploads = models.ManyToManyField('Media', related_name='saved_by_users', blank=True)
    is_private = models.BooleanField(default=False)  # New field to track privacy
    email_confirmed = models.BooleanField(default=False)  # New field to track email confirmation
    firebase_uid = models.CharField(max_length=255, blank=True, null=True)  # Field to store Firebase UID

    def __str__(self):
        return self.user.username


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
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(AuthUser, related_name='liked_uploads', blank=True)
    view_count = models.PositiveIntegerField(default=0)  # To keep track of views
    reported_by = models.ManyToManyField(AuthUser, related_name='reported_media', blank=True)  #report
    report_count = models.IntegerField(default=0)
    tags = models.ManyToManyField(AuthUser, related_name='tagged_media', blank=True)  # New field for tagging users
    is_private = models.BooleanField(default=False)  # New field to track privacy
    
    def __str__(self):
        return self.description

    def delete_file(self):
        if self.file:
            self.file.delete(save=False)


class Story(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='stories')
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='stories')
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
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE)
    liked_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags liked by the user
    not_interested_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags marked as not interested by the user
    viewed_hashtags = models.JSONField(default=list)  # Store the last 50 unique hashtags viewed by the user
    viewed_media = models.JSONField(default=list)  # Store the last viewed media IDs
    not_interested_media = models.JSONField(default=list)  # Store the last 50 unique media IDs that the user is not interested in

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