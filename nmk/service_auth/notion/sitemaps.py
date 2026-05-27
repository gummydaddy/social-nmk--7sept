from django.contrib.sitemaps import Sitemap
from .models import Notion
from django.utils.timezone import now
from django.urls import reverse
from django.utils.html import escape


class NotionSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return Notion.objects.filter(deletion_date__gt=now())

    def lastmod(self, obj):
        return obj.created_at

    def priority(self, obj):
        return 0.7

    def location(self, obj):
        return reverse('notion:notion_detail', kwargs={
            'username': obj.user.username,
            'notion_id': obj.id
        })

    def get_urls(self, page=1, site=None, protocol=None):
        urls = super().get_urls(page=page, site=site, protocol=protocol)
        for url_info, obj in zip(urls, self.paginator.page(page).object_list):
            url_info["description"] = obj.content or ""
        return urls
