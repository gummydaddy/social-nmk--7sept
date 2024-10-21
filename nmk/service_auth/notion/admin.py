from django.contrib import admin
from .models import Notion, Follow, Notification, Comment, Hashtag, BlockedUser
# Register your models here.


# admin.site.register(Notion)  # Register Group model with the custom admin site
admin.site.register(Follow)  # Register Group model with the custom admin site
# admin.site.register(Like)  # Register Group model with the custom admin site
admin.site.register(Notification)  # Register Group model with the custom admin site
admin.site.register(Hashtag)  # Register Group model with the custom admin site
admin.site.register(BlockedUser)  # Register Group model with the custom admin site


@admin.register(Notion)
class NotionAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_content', 'created_at')

    def display_content(self, obj):
        return obj.content
    display_content.short_description = 'Content'

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_content', 'created_at')

    def display_content(self, obj):
        return obj.content
    display_content.short_description = 'Content'