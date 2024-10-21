from rest_framework import serializers
from .models import Media
from service_auth.notion.models import Comment

class CommentSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username')

    class Meta:
        model = Comment
        fields = ['id', 'user_username', 'content', 'created_at']

class MediaSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username')
    comments = CommentSerializer(many=True, read_only=True)
    is_video = serializers.SerializerMethodField()
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)

    class Meta:
        model = Media
        fields = ['id', 'user_username', 'description', 'file_url', 'is_video', 'comments', 'likes_count']

    def get_is_video(self, obj):
        return obj.file.url.endswith('.mp4')
