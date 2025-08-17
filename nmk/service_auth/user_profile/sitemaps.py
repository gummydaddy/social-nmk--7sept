from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Profile
from .models import Media
from django.utils.timezone import now
from django.utils.html import escape

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return ['only_card:landing_page', 'user_profile:following_media', 'only_message:message_list_view']

    def location(self, item):
        return reverse(item)
'''
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
'''



class ProfileSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Profile.objects.filter(is_private=False)

    def lastmod(self, obj):
        return obj.user.date_joined

    def priority(self, obj):
        return 1.0 if obj.country == 'IN' else 0.5

    def location(self, obj):
        return reverse('user_profile:profile_detail', kwargs={'username': obj.user.username})


class MediaSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return Media.objects.filter(is_private=False, is_story=False, is_processed=True)

    def lastmod(self, obj):
        return obj.created_at

    def priority(self, obj):
        return 1.0 if obj.country == 'IN' else 0.6

    def location(self, obj):
        return reverse('user_profile:media_detail', kwargs={
            'username': obj.user.username,
            'media_id': obj.id
        })
    '''
    def get_urls(self, page=1, site=None, protocol=None):
        urls = super().get_urls(page=page, site=site, protocol=protocol)
        for url_info, obj in zip(urls, self.paginator.page(page).object_list):
            description = escape(obj.description or "")
            url_info["description"] = description
        return urls
 
    '''
    def get_urls(self, page=1, site=None, protocol=None):
        urls = super().get_urls(page=page, site=site, protocol=protocol)
        for url_info, obj in zip(urls, self.paginator.page(page).object_list):
            # Full absolute URL for the image thumbnail
            image_url = f"{protocol}://{site.domain}{obj.thumbnail.url}" if obj.thumbnail else None
            
            url_info["image_loc"] = image_url
            url_info["image_title"] = obj.description.split('\n')[0] if obj.description else ""
            url_info["image_caption"] = obj.description or ""
        return urls
