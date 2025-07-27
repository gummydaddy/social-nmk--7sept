from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Profile
from .models import Media
from django.utils.timezone import now

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return ['only_card:landing_page', 'user_profile:following_media', 'only_message:message_list_view']

    def location(self, item):
        return reverse(item)

class ProfileSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Profile.objects.filter(is_private=False)

    def lastmod(self, obj):
        return obj.user.date_joined  # Or any other field if you track updates

    def priority(self, obj):
        return 1.0 if obj.country == 'IN' else 0.5


class MediaSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return Media.objects.filter(is_private=False, is_story=False, is_processed=True)

    def lastmod(self, obj):
        return obj.created_at

    def priority(self, obj):
        return 1.0 if obj.country == 'IN' else 0.6

