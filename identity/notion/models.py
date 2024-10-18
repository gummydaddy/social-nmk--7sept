# your_app/models.py

from django.db import models
from django.contrib.auth.models import User as AuthUser
from .fields import CompressedTextField
from user_profile.models import Media
from django.utils.timezone import now #new
from django.utils import timezone
from datetime import timedelta


class Hashtag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

def get_deletion_date():
    return now() + timedelta(days=1)


class Notion(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='notions')
    content = CompressedTextField()
    created_at = models.DateTimeField(auto_now_add=True)
    hashtags = models.ManyToManyField(Hashtag, related_name='notions', blank=True)
    tagged_users = models.ManyToManyField(AuthUser, related_name='tagged_notions', blank=True)
    likes = models.ManyToManyField(AuthUser, related_name='liked_notions', blank=True)  # Now directly a ManyToManyField for likes
    deletion_date = models.DateTimeField(default=get_deletion_date, db_index=True)  # Use the function instead of lambda
    # deletion_date = models.DateTimeField(default=lambda: now() + timedelta(days=1), db_index=True) #new with line 7 import 

    def __str__(self):
        return self.content
    
#block     
class BlockedUser(models.Model):
    blocker = models.ForeignKey(AuthUser, related_name='blocker', on_delete=models.CASCADE)
    blocked = models.ForeignKey(AuthUser, related_name='blocked', on_delete=models.CASCADE)
    blocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')

    def __str__(self):
        return f'{self.blocker.username} blocked {self.blocked.username}'
    

class Follow(models.Model):
    follower = models.ForeignKey(AuthUser, related_name='following_set', on_delete=models.CASCADE)
    following = models.ForeignKey(AuthUser, related_name='follower_set', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'following')
        # or alternatively:
        # constraints = [
        #     models.UniqueConstraint(fields=['follower', 'following'], name='unique_followers')
        # ]

class Comment(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='comments')
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='comments', null=True)
    notion = models.ForeignKey(Notion, on_delete=models.CASCADE, related_name='comments',null=True )
    content = CompressedTextField()
    likes = models.ManyToManyField(AuthUser, related_name='liked_comments', blank=True)  # Now directly a ManyToManyField for likes
    dislikes = models.ManyToManyField(AuthUser, related_name='disliked_comments', blank=True)  # Now directly a ManyToManyField for likes
    created_at = models.DateTimeField(auto_now_add=True)
    hashtags = models.ManyToManyField(Hashtag, related_name='comments', blank=True)
    tagged_users = models.ManyToManyField(AuthUser, related_name='tagged_comments', blank=True)

    def __str__(self):
        return self.content

class Notification(models.Model):
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='notifications', null = True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    notion = models.ForeignKey('Notion', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications')
    comment = models.ForeignKey('Comment', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications')
    liked_by = models.ForeignKey(AuthUser, null=True, blank=True, on_delete=models.CASCADE, related_name='liked_notifications')
    related_media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='related_notifications', null=True, blank=True)
    related_notion = models.ForeignKey(Notion, on_delete=models.CASCADE, related_name='related_notifications', null=True, blank=True)
    related_comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='related_notifications', null=True, blank=True)
    related_user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='related_notifications', null=True, blank=True)
    type = models.CharField(max_length=50, choices=[('follow', 'Follow'), ('like', 'Like'), ('comment', 'Comment')], null=True)


    def __str__(self):
        return self.content
