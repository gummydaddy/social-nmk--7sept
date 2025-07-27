from django.contrib.sitemaps import Sitemap
from .models import Notion
from django.utils.timezone import now


class NotionSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return Notion.objects.filter(deletion_date__gt=now())

    def lastmod(self, obj):
        return obj.created_at

    def priority(self, obj):
        return 0.7
