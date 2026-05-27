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
from django_redis import get_redis_connection

redis_client = redis.StrictRedis(
    host=getattr(settings, "REDIS_HOST", "localhost"),
    port=getattr(settings, "REDIS_PORT", 6379),
    db=0,
    decode_responses=True,
)

#TRENDING_KEY = "media_trending_scores"
TRENDING_ZSET_KEY = "media_trending_scores"
TRENDING_WINDOW_DAYS = 5
TRENDING_CACHE_EXPIRY_MINUTES = 1800


def set_trending_score(media_id, score, expiry_minutes=TRENDING_CACHE_EXPIRY_MINUTES):
    """
    Cache trending score with expiry.
    
    Args:
        media_id: ID of the media
        score: Calculated trending score
        expiry_minutes: How long to keep the entire sorted set
    """
    try:
        redis_client.zadd(TRENDING_ZSET_KEY, {str(media_id): score})
        redis_client.expire(TRENDING_ZSET_KEY, expiry_minutes * 60)
        return True
    except Exception as e:
        print(f"Error setting trending score: {e}")
        return False


def get_trending_media_ids(limit=50):
    """
    Fetch top trending media IDs from Redis sorted set.
    
    Args:
        limit: Number of top trending media to fetch
        
    Returns:
        List of media IDs (integers) sorted by trending score (highest first)
    """
    try:
        redis_conn = get_redis_connection("default")
        # ZREVRANGE = highest score first
        ids = redis_conn.zrevrange(TRENDING_ZSET_KEY, 0, limit - 1)
        # Redis returns bytes → convert to ints
        return [int(i) for i in ids] if ids else []
    except Exception as e:
        print(f"Error getting trending media IDs: {e}")
        return []


def get_top_trending(limit=20):
    """
    Fetch top trending media IDs with their scores.
    
    Args:
        limit: Number of top trending media to fetch
        
    Returns:
        List of tuples [(media_id, score), ...]
    """
    try:
        results = redis_client.zrevrange(TRENDING_ZSET_KEY, 0, limit - 1, withscores=True)
        return [(int(mid), score) for mid, score in results]
    except Exception as e:
        print(f"Error getting top trending with scores: {e}")
        return []


def get_trending_score(media_id):
    """
    Get the trending score for a specific media.
    
    Args:
        media_id: ID of the media
        
    Returns:
        Float score or 0.0 if not found
    """
    try:
        redis_conn = get_redis_connection("default")
        score = redis_conn.zscore(TRENDING_ZSET_KEY, str(media_id))
        return float(score) if score is not None else 0.0
    except Exception as e:
        print(f"Error getting trending score for media {media_id}: {e}")
        return 0.0


def get_trending_scores_batch(media_ids):
    """
    Get trending scores for multiple media IDs in one batch operation.
    
    Args:
        media_ids: List of media IDs
        
    Returns:
        Dictionary mapping media_id (str) -> score (float)
    """
    try:
        redis_conn = get_redis_connection("default")
        str_ids = [str(mid) for mid in media_ids]
        scores = redis_conn.zmscore(TRENDING_ZSET_KEY, str_ids)
        
        return {
            str(media_id): float(score) if score is not None else 0.0
            for media_id, score in zip(media_ids, scores)
        }
    except Exception as e:
        print(f"Error getting batch trending scores: {e}")
        return {str(mid): 0.0 for mid in media_ids}


def clear_trending_cache():
    """Clear the entire trending cache."""
    try:
        redis_client.delete(TRENDING_ZSET_KEY)
        return True
    except Exception as e:
        print(f"Error clearing trending cache: {e}")
        return False


def remove_media_from_trending(media_id):
    """
    Remove a specific media from trending cache.
    Useful when media is deleted or made private.
    
    Args:
        media_id: ID of the media to remove
    """
    try:
        redis_conn = get_redis_connection("default")
        redis_conn.zrem(TRENDING_ZSET_KEY, str(media_id))
        return True
    except Exception as e:
        print(f"Error removing media {media_id} from trending: {e}")
        return False
#____________________________________





# -------------------------------------------------------------------------------------------------------------------
# Helper utilities for global cache to be used for display cache media globaly to all with the updated view functions 
# -------------------------------------------------------------------------------------------------------------------

# ---------------------
# Global cache constants
# ---------------------

from .models import Media, Profile, UserHashtagPreference, Buddy, Engagement
from  service_auth.notion.models import Follow, BlockedUser

GLOBAL_EXPLORE_CACHE_KEY = "global_explore_media_v4"  # bump version when changing shape
GLOBAL_EXPLORE_CACHE_TIMEOUT = 3000                     # 50 minutes
GLOBAL_EXPLORE_CAP = 400                               # how many items to keep in the global cache



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
        #"likes_count": getattr(m, "likes", None).count() if getattr(m, "likes", None) else 0,
        "likes_count": getattr(m, "likes_count", 0),

        "view_count": getattr(m, "view_count", 0),
        "is_private": bool(getattr(m, "is_private", False)),
        "hashtags": hashtag_names,
        "profile_picture_url": profile_picture_url,
    }



def build_and_cache_global_explore():
    logger.info("Building global explore cache (up to %d items)", GLOBAL_EXPLORE_CAP)

    ids = list(
        Media.objects.filter(is_private=False)
        .order_by('-created_at')
        .values_list('id', flat=True)[:GLOBAL_EXPLORE_CAP]
    )

    cache.set(GLOBAL_EXPLORE_CACHE_KEY, ids, GLOBAL_EXPLORE_CACHE_TIMEOUT)
    logger.info("Cached %d global explore IDs", len(ids))
    return ids



def get_global_explore_ids(limit=GLOBAL_EXPLORE_CAP):
    ids = cache.get(GLOBAL_EXPLORE_CACHE_KEY)
    if ids:
        return ids

    ids = list(
        Media.objects.filter(is_private=False)
        .order_by('-created_at')
        .values_list('id', flat=True)[:limit]
    )

    cache.set(GLOBAL_EXPLORE_CACHE_KEY, ids, GLOBAL_EXPLORE_CACHE_TIMEOUT)
    return ids



def get_media_qs_from_cached_ids(ids: List[int], exclude_ids: set, limit: int = 300, user=None):
    filtered_ids = [mid for mid in ids if mid not in exclude_ids][:limit]

    if not filtered_ids:
        return Media.objects.none()

    # Preserve Redis ranking order
    ordering = Case(*[When(id=pk, then=pos) for pos, pk in enumerate(filtered_ids)])

    qs = (
        Media.objects.filter(id__in=filtered_ids, is_private=False)
        .select_related('user', 'user__profile')
        .prefetch_related('hashtags')
        .annotate(likes_count=Count('likes', distinct=True))
        .order_by(ordering)
    )

    if user and user.is_authenticated:
        qs = qs.annotate(
            is_liked=Exists(
                Engagement.objects.filter(
                    media=OuterRef('pk'),
                    user=user,
                    engagement_type='like'
                )
            )
        )

    return qs

# -------------------------------------------------------------------------------------------------------------------
# Helper utilities for global cache to be used for display cache media globaly to all with the updated view functions
# -------------------------------------------------------------------------------------------------------------------

