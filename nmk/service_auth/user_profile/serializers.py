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

    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        #fields = ['id', 'user_username', 'description', 'file_url', 'is_video', 'comments', 'likes_count']
        fields = [
            "id", "description", "created_at", "category",
            "user_username", "likes_count", "is_video", "thumbnail_url",
            "is_private", 'file_url', 'comments',
        ]

    def get_is_video(self, obj):
        return obj.file.url.endswith('.mp4')

    #api_integration
    def get_user(self, obj):
        return MediaUserMinimalSerializer({"id": obj.user_id, "username": obj.user.username}).data

    def get_thumbnail_url(self, obj):
        thumb = getattr(obj, "thumbnail", None)
        return getattr(thumb, "url", None) if thumb else None


class MediaUserMinimalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_username = serializers.CharField()
