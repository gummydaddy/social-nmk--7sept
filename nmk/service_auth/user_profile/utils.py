# user_profile/utils.py
from service_auth.user_profile.models import AuthUser
from django.urls import reverse, NoReverseMatch
import re
from collections import deque
from django.utils.html import escape, mark_safe
from django.contrib.auth import get_user_model
import bleach
from django.db import IntegrityError
from django.http import HttpResponse
from django.template.loader import render_to_string
import base64
from datetime import timedelta

import redis
from django.conf import settings
from django.utils import timezone

from django.db.models import Count, Exists, OuterRef, Q
from django.core.cache import cache
from typing import List, Dict
import itertools
import logging
logger = logging.getLogger(__name__)


def linkify(text):
    """
    Convert URLs to clickable links.
    """
    url_pattern = re.compile(r'(https?://[^\s]+)')
    text = url_pattern.sub(lambda x: f'<a href="{x.group(0)}" target="_blank">{x.group(0)}</a>', text)
    return bleach.clean(text)

class HashtagQueue:
    def __init__(self, max_size=50):
        self.queue = deque(maxlen=max_size)

    def add_hashtags(self, hashtags):
        for hashtag in hashtags:
            if hashtag in self.queue:
                self.queue.remove(hashtag)
            self.queue.append(hashtag)

    def get_hashtags(self):
        return list(self.queue)

hashtag_queue = HashtagQueue()

'''
def add_to_fifo_list(fifo_list, item, max_length=50):
    if item in fifo_list:
        fifo_list.remove(item)
    fifo_list.append(item)
    if len(fifo_list) > max_length:
        fifo_list.pop(0)
    return fifo_list
'''

def add_to_fifo_list(fifo_list, item, max_length=50):
    """
    Adds an item to a list acting as a FIFO queue, ensuring uniqueness and capped size.
    Safe for Django JSONFields (uses lists, not deque).
    """
    fifo_list = fifo_list or []
    if item in fifo_list:
        fifo_list.remove(item)
    fifo_list.append(item)
    if len(fifo_list) > max_length:
        fifo_list = fifo_list[-max_length:]
    return fifo_list


#________________________________
#for view tracking in future
def track_media_view(user, media):
    """
    Records a unique view engagement for a given user and media.
    Updates view_count and user preferences.
    """
    if not user.is_authenticated:
        return False
    if media.user_id == user.id:  # Don't track if it's their own media
        return False

    from .models import Engagement, UserHashtagPreference

    try:
        engagement, created = Engagement.objects.get_or_create(
            media=media,
            user=user,
            engagement_type='view'
        )
    except IntegrityError:
        return False

    if created:
        # Update view_count
        media.view_count = Engagement.objects.filter(
            media=media,
            engagement_type='view'
        ).count()
        media.save(update_fields=['view_count'])

        # Update preferences
        pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        viewed = list(pref.viewed_media or [])
        if media.id not in viewed:
            viewed.append(media.id)
            pref.viewed_media = viewed[-50:]  # Keep only latest 50
            pref.save(update_fields=['viewed_media'])

        return True
    return False

#____________________________________

#____________________________________
#

def strip_html_tags(text):
    return re.sub(r'<.*?>', '', text)

def make_usernames_clickable(content):
    def replace_username(match):
        username = match.group(1)
        try:
            user = AuthUser.objects.select_related('profile').get(username=username)

            if user.profile and user.profile.profile_picture:
                # Get the raw string URL and strip any HTML tags
                profile_pic_url = strip_html_tags(str(user.profile.profile_picture.url))
            else:
                profile_pic_url = '/static/images/default_profile.png'

            profile_url = reverse("user_profile:profile", args=[user.id])

            return mark_safe(
                f'''
                <span class="mention-with-avatar">
                    <a href="{profile_url}">
                        <img src="{profile_pic_url}" class="mention-avatar" alt="{username}'s profile picture">
                        @{username}
                    </a>
                </span>
                '''
            )
        except AuthUser.DoesNotExist:
            return f'@{username}'

    # Replace @usernames with avatar + link
    content = re.sub(r'@(\w+)', replace_username, content)

    # Replace URLs with clickable links — BUT only in main text, not inside img tags
    content = re.sub(r'(?<!src=")(https?://\S+)', r'<a href="\1" target="_blank">\1</a>', content)

    return content

#
#______________________________________


##__________________________________
# util for bots and crawlers
BOT_USER_AGENTS = [
    "googlebot", "bingbot", "twitterbot",
    "facebookexternalhit", "linkedinbot", "slackbot",
    "discordbot", "applebot", "facebot", "instagram",
    "whatsapp", "discordbot", "pinterest", "yandexbot", "duckduckbot"
]

def is_bot_request(request):
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(bot in ua for bot in BOT_USER_AGENTS)

def bot_meta_response(template_name, context):
    """Return an HTML response with proper meta tags for bots."""
    html = render_to_string(template_name, context)
    return HttpResponse(html)

'''
def normalize_media_url(url: str) -> str:
    """Force media URLs to use media.socyfie.com domain."""
    if not url:
        return url
    return re.sub(r"^https?://[^/]+/", "https://media.socyfie.com/", url)
'''


#______________________________________
#


#_____________________________________
#for sharing of media directly from the gallery withoutopening the app

def store_shared_file_in_session(request, file):
    """Store shared file in user session."""
    request.session['shared_file_name'] = file.name
    request.session['shared_file_content'] = file.read()

def get_shared_file_from_session(request):
    """Retrieve and remove shared file from session."""
    file_name = request.session.pop('shared_file_name', None)
    file_content = request.session.pop('shared_file_content', None)
    if file_name and file_content:
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        return {'file': file_name, 'content': encoded_content}
    return {'file': None, 'content': None}

#____________________________________



#___________________________________
# for media universal trending score 
# Connect to Redis
redis_client = redis.StrictRedis(
    host=getattr(settings, "REDIS_HOST", "localhost"),
    port=getattr(settings, "REDIS_PORT", 6379),
    db=0,
    decode_responses=True,
)

TRENDING_KEY = "media_trending_scores"

def set_trending_score(media_id, score, expiry_minutes=120):
    """Cache trending score with expiry."""
    redis_client.zadd(TRENDING_KEY, {str(media_id): score})
    redis_client.expire(TRENDING_KEY, expiry_minutes * 60)

def get_top_trending(limit=20):
    """Fetch top trending media IDs from cache."""
    return [int(mid) for mid, _ in redis_client.zrevrange(TRENDING_KEY, 0, limit - 1, withscores=True)]

def clear_trending_cache():
    redis_client.delete(TRENDING_KEY)

#____________________________________





# -------------------------------------------------------------------------------------------------------------------
# Helper utilities for global cache to be used for display cache media globaly to all with the updated view functions 
# -------------------------------------------------------------------------------------------------------------------

# ---------------------
# Global cache constants
# ---------------------

from .models import Media, Profile, UserHashtagPreference, Buddy, Engagement
from  service_auth.notion.models import Follow, BlockedUser

GLOBAL_EXPLORE_CACHE_KEY = "global_explore_media_v2"  # bump version when changing shape
GLOBAL_EXPLORE_CACHE_TIMEOUT = 300                     # 5 minutes
GLOBAL_EXPLORE_CAP = 200                               # how many items to keep in the global cache



def _serialize_media_for_cache(m: Media) -> Dict:
    """
    Defensive serializer used when we want to store some metadata in the cache.
    Note: In this design we actually store ONLY ids in the global cache for safety and
    to make invalidation + ordering simple. This function is kept for completeness if
    you want to store richer metadata later (but avoid storing model instances).
    """
    # get hashtag names as list of strings (safe primitives)
    try:
        hashtag_names = [h.name for h in m.hashtags.all()]
    except Exception:
        hashtag_names = []

    # profile picture url guard
    try:
        profile_picture_url = m.user.profile.profile_picture.url if getattr(m.user, 'profile', None) and m.user.profile.profile_picture else None
    except Exception:
        profile_picture_url = None

    return {
        "id": int(m.id),
        "created_at": m.created_at.isoformat() if getattr(m, "created_at", None) else None,
        "user_id": m.user.id if getattr(m, "user", None) else None,
        "username": m.user.username if getattr(m, "user", None) else None,
        "description": m.description or "",
        "media_type": m.media_type or ( "video" if (m.file.name.lower().endswith('.mp4') if getattr(m, 'file', None) else False) else "image"),
        "thumbnail_url": getattr(m, "thumbnail", None).url if getattr(m, "thumbnail", None) else None,
        "file_url": getattr(m, "file", None).url if getattr(m, "file", None) else None,
        "likes_count": getattr(m, "likes", None).count() if getattr(m, "likes", None) else 0,
        "view_count": getattr(m, "view_count", 0),
        "is_private": bool(getattr(m, "is_private", False)),
        "hashtags": hashtag_names,
        "profile_picture_url": profile_picture_url,
    }


def build_and_cache_global_explore():
    """
    Build the global explore list and store only the list of media IDs (ordered newest-first).
    We store only IDs to keep the cache compact and avoid pickling heavy ORM models.
    """
    logger.info("Building global explore cache (up to %d items)", GLOBAL_EXPLORE_CAP)
    # Query the DB for latest public media (exclude private uploads)
    qs = (
        Media.objects.filter(is_private=False)

        #Media.objects.filter(
            #is_private=False,
            #user__profile__is_private=False
        #)
        .select_related('user', 'user__profile')
        .prefetch_related('hashtags')
        .order_by('-created_at')[:GLOBAL_EXPLORE_CAP]
    )

    ids = [int(m.id) for m in qs]
    # Save only the ID list in Redis
    cache.set(GLOBAL_EXPLORE_CACHE_KEY, ids, GLOBAL_EXPLORE_CACHE_TIMEOUT)
    logger.info("Cached %d global explore IDs", len(ids))
    return ids


def get_global_explore_ids() -> List[int]:
    """
    Return the cached list of global explore media IDs, building it if missing.
    """
    ids = cache.get(GLOBAL_EXPLORE_CACHE_KEY)
    if ids is None:
        try:
            ids = build_and_cache_global_explore()
        except Exception as e:
            logger.exception("Failed to build global explore cache: %s", e)
            # As a fallback, return empty list (caller should handle fallback)
            return []
    return ids


def get_media_qs_from_cached_ids(ids: List[int], exclude_ids: set, limit: int = 300):
    """
    Given the global explore IDs (ordered newest-first), produce a queryset of Media
    for the first `limit` ids that are not in exclude_ids.

    This minimizes DB hits because we only fetch the small slice we need.
    """
    # Filter out already sent ids and preserve order by created_at desc at DB level.
    filtered_ids = [mid for mid in ids if mid not in exclude_ids]
    slice_ids = filtered_ids[:limit]
    if not slice_ids:
        return Media.objects.none()
    # Fetch corresponding Media objects (only these will hit DB)
    qs = (
        Media.objects.filter(id__in=slice_ids)
        .select_related('user', 'user__profile')
        .prefetch_related('hashtags', 'likes')
        .annotate(likes_count=Count('likes'))
        .order_by('-created_at')
    )
    return qs
'''

from django.db.models import Case, When, Count

def get_media_qs_from_cached_ids(
    ids: List[int],
    exclude_ids: set,
    limit: int = 300
):
    """
    Given ordered media IDs (e.g. trending + explore),
    return a queryset preserving that order.
    """

    # Filter out already served IDs
    filtered_ids = [mid for mid in ids if mid not in exclude_ids]
    slice_ids = filtered_ids[:limit]

    if not slice_ids:
        return Media.objects.none()

    # Preserve order using CASE WHEN
    ordering = Case(
        *[When(id=mid, then=pos) for pos, mid in enumerate(slice_ids)]
    )

    qs = (
        Media.objects.filter(id__in=slice_ids)
        .select_related('user', 'user__profile')
        .prefetch_related('hashtags', 'likes')
        .annotate(likes_count=Count('likes'))
        .order_by(ordering)
    )
    return qs
'''

# -------------------------------------------------------------------------------------------------------------------
# Helper utilities for global cache to be used for display cache media globaly to all with the updated view functions
# -------------------------------------------------------------------------------------------------------------------

