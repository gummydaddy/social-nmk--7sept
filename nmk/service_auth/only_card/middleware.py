# middleware.py
from django.shortcuts import redirect
from django.urls import reverse
from .models import CustomGroup

from django.http import HttpResponse
from django.template.loader import render_to_string
from service_auth.user_profile.models import Media
from service_auth.user_profile.utils import is_bot_request, bot_meta_response
from django.shortcuts import get_object_or_404
import logging


class SubgroupApprovalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            approved_subgroups = CustomGroup.objects.filter(users=request.user, is_approved=True)
            if approved_subgroups.exists():
                return redirect(reverse('only_card:subgroup_landing_page'))

        response = self.get_response(request)
        return response




##_____________________________
#for bots and crawlers
"""
class BotMetaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_bot_request(request):
            path_parts = request.path.strip("/").split("/")
            # Example: detect /media/<id> URLs
            if len(path_parts) == 2 and path_parts[0] == "media":
                media_id = path_parts[1]
                media = get_object_or_404(Media, id=media_id)
                return bot_meta_response("meta_preview.html", {
                    "title": media.title,
                    "description": media.description or "View this on Socyfie",
                    "image_url": media.file.url,
                    "url": request.build_absolute_uri(),
                })
        return self.get_response(request)
"""




logger = logging.getLogger(__name__)


BOT_USER_AGENTS = [
    "googlebot", "bingbot", "twitterbot",
    "facebookexternalhit", "linkedinbot", "slackbot",
    "discordbot", "applebot"
]

def is_bot_request(request):
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(bot in ua for bot in BOT_USER_AGENTS)

def bot_meta_response(template_name, context):
    """Return an HTML response with proper meta tags for bots."""
    html = render_to_string(template_name, context)
    return HttpResponse(html)

class BotMetaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_bot_request(request):
            try:
                path_parts = request.path.strip("/").split("/")
                if len(path_parts) == 2 and path_parts[0] == "media":
                    media_id = path_parts[1]
                    media = get_object_or_404(Media, id=media_id)

                    # Safely get fields
                    title = getattr(media, "title", None) or "Media Preview"
                    description = media.description or "View this on Socyfie"
                    image_url = ""
                    try:
                        image_url = media.file.url if media.file else ""
                    except Exception as e:
                        logger.warning(f"Media {media_id} has no file URL: {e}")

                    return bot_meta_response("meta_preview.html", {
                        "title": title,
                        "description": description,
                        "image_url": image_url,
                        "url": request.build_absolute_uri(),
                    })
            except Exception as e:
                logger.exception(f"BotMetaMiddleware error: {e}")
                # fall back to normal view
        return self.get_response(request)

##_________________________________
