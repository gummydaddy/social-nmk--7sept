# middleware.py
from django.shortcuts import redirect
from django.urls import reverse
from .models import CustomGroup
import os
from django.http import HttpResponse
from django.template.loader import render_to_string
from service_auth.user_profile.models import Media

from service_auth.notion.models import Notion
from service_auth.notion.utils import format_notion_preview_text

from service_auth.user_profile.utils import is_bot_request, bot_meta_response
from django.shortcuts import get_object_or_404
import logging
import re

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
    "googlebot", "bingbot", "twitterbot","novellumalcrawl", "oai-searchbot", "perplexitybot", "petalbot",
    "facebookexternalhit", "linkedinbot", "slackbot", "anchorbrowser", "archive.org_bot", "bytespider", "ccbot", "chatgpt-user",
    "discordbot", "applebot", "facebot", "instagram", "gptbot", "claudebot", "meta-externalagent","amazonbot", "claude-searchbot",
    "whatsapp", "discordbot", "pinterest", "yandexbot", "duckduckbot", "claude-user", "duckassistbot", "facebookbot", "google-cloudvertexbot"
]



def is_bot_request(request):
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(bot in ua for bot in BOT_USER_AGENTS)

def bot_meta_response(template_name, context):
    """Return an HTML response with proper meta tags for bots."""
    html = render_to_string(template_name, context)
    return HttpResponse(html)


#------------------------------------
#_________
#This updated BotMetaMiddleware adds robust handling for missing or anonymous users by safely resolving the profile URL only when a valid user_id exists.
#It prevents NoReverseMatch errors during bot meta preview generation and ensures consistent fallback behavior for both media and notion previews.
#_________
#___________________________________
class BotMetaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):


        # NEVER process these
        EXCLUDED_PREFIXES = (
            "/static/",
            "/media/",
            "/admin/",
            "/favicon.ico",
        )

        if request.path.startswith(EXCLUDED_PREFIXES):
            return self.get_response(request)


        if is_bot_request(request):
            try:
                path_parts = request.path.strip("/").split("/")

                # --- Media preview handler ---
                if len(path_parts) == 2 and path_parts[0] == "media":
                    media_id = path_parts[1]
                    media = get_object_or_404(Media, id=media_id)

                    # Title & description
                    title = getattr(media, "title", None) or f"{media.user.username} on Socyfie"
                    description = media.description or "View this on Socyfie"

                    # Normalize media URL (ensure media.socyfie.com domain)
                    image_url = ""
                    if media.file:
                        try:
                            file_url = media.file.url
                            image_url = re.sub(
                                r"^https?://[^/]+/",
                                "https://media.socyfie.com/",
                                file_url
                            )
                        except Exception as e:
                            logger.warning(f"Media {media_id} has no file URL: {e}")

                    # --- Safe profile URL handling ---
                    try:
                        if getattr(media.user, "id", None):
                            profile_url = reverse("profile", kwargs={"user_id": media.user.id})
                        else:
                            profile_url = reverse("profile")
                    except Exception:
                        profile_url = ""  # Fallback if route not found

                    return bot_meta_response("meta_preview.html", {
                        "title": title,
                        "description": description,
                        "image_url": image_url,
                        "url": request.build_absolute_uri(),
                        "profile_url": profile_url,
                    })

                # --- Notion preview handler ---
                if len(path_parts) == 2 and path_parts[0] == "notion":
                    notion_id = path_parts[1]
                    notion = get_object_or_404(Notion, id=notion_id)

                    title = f"Notion by {notion.user.username}"
                    description = notion.content or "Check out this notion on Socyfie"

                    image_url = ""
                    try:
                        if getattr(notion.user, "id", None):
                            profile_url = reverse("profile", kwargs={"user_id": notion.user.id})
                        else:
                            profile_url = reverse("profile")
                    except Exception:
                        profile_url = ""

                    return bot_meta_response("meta_preview.html", {
                        "title": title,
                        "description": description,
                        "image_url": image_url,
                        "url": request.build_absolute_uri(),
                        "profile_url": profile_url,
                    })

            except Exception as e:
                logger.exception(f"BotMetaMiddleware error: {e}")
                # Fall back to normal view if meta generation fails

        return self.get_response(request)




##_________________________________
