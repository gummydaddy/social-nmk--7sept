
import os
import json
import math
import random
import time

from django.shortcuts import render, get_object_or_404, redirect
from PIL import Image, ImageFilter, ImageOps, ExifTags
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib import messages
from service_auth.notion.models import Follow, Notification, Comment, Hashtag, BlockedUser
from django.views.generic import ListView
from .models import Media, Profile, Engagement, AdminNotification, UserHashtagPreference, Story, Buddy, Audio#, Comment
from .forms import MediaForm, ProfileForm, CommentForm, AudioForm, CategorySelectionForm, CountrySelectionForm
from django.core.files.storage import get_storage_class
from .storage import CompressedMediaStorage

from service_auth.notion.forms import UsernameUpdateForm
from PIL import Image, ImageFilter, ImageOps
import io
import tempfile
from moviepy.editor import VideoFileClip, AudioFileClip
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from .serializers import MediaSerializer
from django.views.decorators.http import require_POST
from .utils import linkify, hashtag_queue, add_to_fifo_list, make_usernames_clickable, store_shared_file_in_session, get_shared_file_from_session
from .utils import is_bot_request, bot_meta_response

from .utils import (
    GLOBAL_EXPLORE_CACHE_KEY,
    GLOBAL_EXPLORE_CACHE_TIMEOUT,
    GLOBAL_EXPLORE_CAP,
    build_and_cache_global_explore,
    get_global_explore_ids,
    get_media_qs_from_cached_ids,
    get_trending_media_ids,
    _serialize_media_for_cache,
    TRENDING_ZSET_KEY,
    TRENDING_WINDOW_DAYS
)

#from .utils import normalize_media_url
import re
from django.db.models import F, Count, Q, Exists, OuterRef
from django.http import JsonResponse
from django.core.cache import cache
# from async_views import async_views

from .tasks import process_media_upload, process_profile_images, WINDOW_SECONDS

import base64
from bs4 import BeautifulSoup

from django.views.decorators.cache import cache_page, cache_control
from django.utils.decorators import method_decorator
import asyncio


import random
from collections import deque, defaultdict
from django.template.loader import render_to_string
from django.utils.html import escape, mark_safe
from django.urls import reverse
from random import shuffle
from django.utils.http import urlencode
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_headers
from django.core.files.uploadedfile import InMemoryUploadedFile
from datetime import datetime, timedelta
from django.utils.timezone import now

from django_redis import get_redis_connection

from django.db import IntegrityError

#from service_auth.utils.scoring import compute_personal_adjustment, apply_diversity_decay

#from .media_utils import score_related_media

#_________________________
#___to open the shared links in the installed pwa__
def open_bridge(request):
    target_url = request.GET.get("url", "https://socyfie.com")
    title = request.GET.get("title", "Socyfie Post")
    description = request.GET.get("desc", "Check out this upload on Socyfie!")
    image_url = request.GET.get("img")

    return render(request, "open.html", {
        "title": title,
        "description": description,
        "image_url": image_url,
        "target_url": target_url,
        "url": request.build_absolute_uri(),

    })

#_________________________
#___to open the shared links in the installed pwa__

# Define constants for scoring weights
LIKED_HASHTAG_WEIGHT = 8
NOT_INTERESTED_HASHTAG_WEIGHT = -10
VIEWED_HASHTAG_WEIGHT = 2
SEARCH_HASHTAG_WEIGHT = 10

FOLLOWED_USER_MEDIA_WEIGHT = 20
FOLLOWED_USER_DESCRIPTION_WEIGHT = 7

ACTIVE_USER_WEIGHT = 2
HIGH_ENGAGEMENT_WEIGHT = 10

#HIGH_FOLLOWER_THRESHOLD = 100_000
HIGH_FOLLOWER_THRESHOLD = 80
HIGH_INFLUENCER_BOOST = 6

CATEGORY_ENGAGEMENT_WEIGHT = 13
FRESHNESS_WEIGHT = 10
DIVERSITY_DECAY_RATE = 0.5
MAX_VIEWED_MEDIA_CACHE = 69
FALLBACK_MEDIA_COUNT = 24
#for cacshing media in explore_detail for 20 min delay 
COOLDOWN_MINUTES = 20
DESCRIPTION_PRIORITY_UNIT = 5   # points per overlapping word (kept modest)

SCORING_NOISE = 3.0
PERSONALIZED_POOL_SIZE = 30  # From collaborative filtering
CATEGORY_POOL_SIZE = 50      # From category matching

#__________________________
#Caching
#Hashtag-Based Scoring
#Followed Users Boost
#Followed Users Boost
#High Engagement Boost
#Influencer Boost
#Category Preference
#Category Preference
#Recency Boost
#Integration for Personalization
#This function allows feed system (following_media) to serve highly personalized media,
#optimized for performance with caching, scoring by social context, engagement, and user interests.
#_______________________________
def calculate_media_score(
    media,
    liked_hashtags,
    not_interested_hashtags,
    viewed_hashtags,
    search_hashtags,
    user_category_preferences,
    followed_users_media_ids=set(),
    followed_users_descriptions_matches=False,
    user=None,
):
    """
    Calculate media score with personalization, recent interest bonuses,
    and Redis caching for repeated access.
    """
    cache_key = f"media_score:{media.id}:{user.id if user else 'anon'}"
    cached_score = cache.get(cache_key)
    if cached_score is not None:
        return cached_score

    score = 0

    # -------------------------
    # Hashtag weights
    # -------------------------
    media_hashtags = [
        h.name for h in getattr(media, "_prefetched_objects_cache", {}).get("hashtags", media.hashtags.all())
    ]
    for hashtag in media_hashtags:
        if hashtag in not_interested_hashtags:
            score += NOT_INTERESTED_HASHTAG_WEIGHT
        if hashtag in viewed_hashtags:
            score += VIEWED_HASHTAG_WEIGHT
        if hashtag in search_hashtags:
            score += SEARCH_HASHTAG_WEIGHT
        if user and hasattr(user, "recent_interest_hashtags") and hashtag in user.recent_interest_hashtags:
            score += 5  # recent like bonus

    # -------------------------
    # Followed users boosts
    # -------------------------
    if media.id in followed_users_media_ids:
        score += FOLLOWED_USER_MEDIA_WEIGHT
    if followed_users_descriptions_matches:
        score += FOLLOWED_USER_DESCRIPTION_WEIGHT

    # -------------------------
    # Active user boost
    # -------------------------
    user_post_count = getattr(media.user, "media_count", None)
    if user_post_count is None and hasattr(media.user, "media"):
        user_post_count = len(getattr(media.user, "_prefetched_objects_cache", {}).get("media", []))
    if user_post_count and user_post_count > 10:
        score += ACTIVE_USER_WEIGHT

    # -------------------------
    # High engagement boost
    # -------------------------
    if getattr(media, "likes_count", 0) > 50:
        score += HIGH_ENGAGEMENT_WEIGHT

    # -------------------------
    # Influencer boost
    # -------------------------
    high_follower_users = set()
    likes = getattr(media, "_prefetched_objects_cache", {}).get("likes", media.likes.all())
    for u in likes:
        follower_count = getattr(u, "follower_count", None)
        if follower_count is None:
            follower_count = len(getattr(u, "_prefetched_objects_cache", {}).get("follower_set", []))
        if follower_count > HIGH_FOLLOWER_THRESHOLD:
            high_follower_users.add(u)

    if hasattr(media, "views"):
        views = getattr(media, "_prefetched_objects_cache", {}).get("views", media.views.all())
        for v in views:
            u = getattr(v, "user", None)
            if not u:
                continue
            follower_count = getattr(u, "follower_count", None)
            if follower_count is None:
                follower_count = len(getattr(u, "_prefetched_objects_cache", {}).get("follower_set", []))
            if follower_count > HIGH_FOLLOWER_THRESHOLD:
                high_follower_users.add(u)

    if high_follower_users:
        score += HIGH_INFLUENCER_BOOST

    # -------------------------
    # Category preference
    # -------------------------
    if getattr(media, "category", None) in user_category_preferences:
        score += CATEGORY_ENGAGEMENT_WEIGHT
    if user and hasattr(user, "recent_interest_categories") and getattr(media, "category", None) in user.recent_interest_categories:
        score += 8  # recent like bonus for category

    # -------------------------
    # Description words recent interest
    # -------------------------
    if user and hasattr(user, "recent_interest_words"):
        desc_lower = (media.description or "").lower()
        if any(word in desc_lower for word in user.recent_interest_words):
            score += 12

    # -------------------------
    # Recency boost
    # -------------------------
    now = timezone.now()
    age_seconds = (now - media.created_at).total_seconds()
    recency_boost = max(0, (86400 * 2 - age_seconds) / 86400)  # boost <2 days
    score += recency_boost


    # -------------------------
    #  old Trending Score Integration directly featches from model-engagement class
    # -------------------------
    # Uses precomputed trending score from model (cached in Redis)
    '''
    try:
        engagement = getattr(media, "engagements", None)
        if engagement:
            trending_score = engagement.first().trending_score
            score += trending_score * 0.4  # weighted contribution
    except Exception:
        pass  # Safe fallback if engagement data missing
    '''

    # -------------------------
    # use this Trending Score Direct Redis Integration when using the newer celery task of update_trending_scores
    # Direct Redis Integration
    #Fetches trending score via key pattern trending_score:{media.id} — matches what your Celery updater likely uses.
    #No DB read — fully cache-based and fast.
    # Weight adjustable
    #Trending influence: score += trending_score * 0.4 (adjust between 0.2–0.6 depending on how “viral” you want the feed to feel).
    # Failsafe
    #If no cache entry, it quietly continues — no DB query or slowdown.
    # Zero migration or model changes needed — pure logic enhancement.
    # -------------------------

    try:
        redis_conn = get_redis_connection("default")
        trending_score = redis_conn.zscore(TRENDING_ZSET_KEY, str(media.id))
        
        if trending_score is not None:
            score += trending_score * 0.4  # Weight trending with 40% influence
        # If not in trending zset, just continue (no penalty)
        
    except Exception as e:
        # Graceful fallback if Redis unavailable
        pass

    # -------------------------
    # Cache and return
    # -------------------------
    cache.set(cache_key, score, timeout=300)  # 5 minutes cache
    return score



#_______________________
#________________________
#bots and crawlers
CRAWLER_AGENTS = [
    "facebookexternalhit",  # Facebook, Messenger
    "facebot",              # Facebook
    "instagram",            # Instagram
    "whatsapp",             # WhatsApp link previews
    "linkedinbot",          # LinkedIn
    "twitterbot",           # Twitter/X
    "slackbot",             # Slack
    "discordbot",           # Discord
    "pinterest",            # Pinterest
    "googlebot",            # Google
    "bingbot",              # Bing
    "yandexbot",            # Yandex
    "duckduckbot",          # DuckDuckGo

    "novellumalcrawl", "oai-searchbot", "perplexitybot", "petalbot",
    "anchorbrowser", "archive.org_bot", "bytespider", "ccbot", "chatgpt-user",
    "applebot", "gptbot", "claudebot", "meta-externalagent","amazonbot", "claude-searchbot",
    "claude-user", "duckassistbot", "facebookbot", "google-cloudvertexbot"
]


def is_crawler(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    return any(bot.lower() in ua for bot in CRAWLER_AGENTS)

#__________________________
#________________________




import logging
logger = logging.getLogger(__name__)



#with video upload support
@login_required
@csrf_exempt
#@cache_page(60 * 2)
def upload_media(request):
    logger.info(f"User {request.user.username} is uploading media")

    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = MediaForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info("MediaForm is valid.")
            media = form.save(commit=False)
            media.user = request.user

            # Assign user's category
            if hasattr(request.user, 'profile') and request.user.profile.category:
                media.category = request.user.profile.category
                logger.info(f"Category '{media.category}' assigned to media by user {request.user.username}")
            else:
                logger.warning(f"User {request.user.username} has no category assigned in their profile")

            # Sanitize description and extract mentions
            media.description = escape(media.description or '')
            hashtags = set(re.findall(r'#(\w+)', media.description))
            tagged_usernames = set(re.findall(r'@(\w+)', media.description))

            file_obj = request.FILES['file']
            file_name = file_obj.name.lower()
            ext = os.path.splitext(file_name)[1]

            is_image = ext in ('.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic')
            is_video = ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm')

            if is_image or is_video:
                media.media_type = 'image' if is_image else 'video'
                media.is_processed = False  # Mark as unprocessed

                # Save media stub to DB (without file)
                media.save()
                form.save_m2m()

                # Save uploaded file to a temporary location
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
                        for chunk in file_obj.chunks():
                            temp.write(chunk)
                        temp_file_path = temp.name
                        logger.info(f"Temporary media file written to {temp_file_path}")
                except Exception as e:
                    logger.error(f"Failed to write temp file: {e}")
                    return JsonResponse({'status': 'temp_file_error'}, status=500)

                # Offload processing to Celery
                process_media_upload.delay(
                    media.id,
                    temp_file_path,
                    file_name,
                    media.media_type,
                    request.POST.get('filter') if is_image else None
                )

                # Mention notifications from description
                for username in tagged_usernames:
                    try:
                        tagged_user = AuthUser.objects.get(username=username)
                        if tagged_user != request.user:
                            Notification.objects.create(
                                user=tagged_user,
                                content=f'{request.user.username} mentioned you in a media description: '
                                        f'<a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                                type='mention',
                                related_user=request.user,
                                related_media=media
                            )
                    except AuthUser.DoesNotExist:
                        logger.warning(f"Tagged user @{username} does not exist")

                # m2m tag notifications
                for tagged_user in media.tags.all():
                    if tagged_user != request.user:
                        Notification.objects.create(
                            user=tagged_user,
                            content=f'{request.user.username} tagged you in a media: '
                                    f'<a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                            type='tag',
                            related_user=request.user,
                            related_media=media
                        )

                return JsonResponse({'status': 'success', 'media_id': media.id})

            else:
                logger.warning(f"Unknown file type uploaded: {file_name}")
                media.media_type = 'unknown'
                media.save()
                form.save_m2m()

                # Get duration and start_time from cleaned_data
                start_time = form.cleaned_data.get('start_time', 0.0)
                duration = form.cleaned_data.get('duration', None)

                # Pass these as task arguments
                process_media_upload.delay(media_instance.id, start_time, duration)

                for tagged_user in media.tags.all():
                    if tagged_user != request.user:
                        Notification.objects.create(
                            user=tagged_user,
                            content=f'{request.user.username} tagged you in a media: '
                                    f'<a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                            type='tag',
                            related_user=request.user,
                            related_media=media
                        )

                return JsonResponse({'status': 'saved_unknown_type'})

        else:
            logger.warning("MediaForm is invalid.")
            return JsonResponse({'status': 'invalid_form'}, status=400)

    else:
        form = MediaForm()

        #new add for catogery update setting
        profile, _ = Profile.objects.get_or_create(user=request.user)
        category_form = CategorySelectionForm(instance=profile)

        return render(request, 'upload.html', {'form': form, 'category_form': category_form})
        #return render(request, 'upload.html', {'form': form,})


@cache_page(60 * 2)
@login_required
def upload_audio(request):
    logger.info(f"User {request.user.username} is uploading audio")
    
    if request.method == 'POST':
        form = AudioForm(request.POST, request.FILES)
        
        if form.is_valid():
            logger.info("AudioForm is valid.")
            audio = form.save(commit=False)
            audio.user = request.user

            # Assign the user's category to the media
            if request.user.profile.category:
                audio.category = request.user.profile.category
                logger.info(f"Category '{audio.category}' assigned to media by user {request.user.username}")
            else:
                logger.warning(f"User {request.user.username} has no category assigned in their profile")

            # Process description to escape HTML tags
            audio.description = escape(audio.description)

            # Use CompressedMediaStorage for saving the file
            storage = CompressedMediaStorage()

            # Handle the uploaded audio file
            if audio.file.name.lower().endswith(('.mp3', '.wav', '.ogg')):
                logger.info(f"Audio file detected: {audio.file.name}")
                audio.media_type = 'audio'

                # Save the uploaded file to a temporary location for processing
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    for chunk in audio.file.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name

                # Load the audio clip using AudioFileClip
                clip = AudioFileClip(temp_file_path)

                # Set duration dynamically based on the clip's actual duration
                duration = clip.duration
                if duration > 3600:
                    duration = 3600  # Ensure it's no longer than 1 hour

                audio.duration = duration  # Set the duration on the model

                subclip = clip.subclip(0, duration)

                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_output_file:
                    output_file_path = temp_output_file.name

                # Write the audio to the output file
                subclip.write_audiofile(output_file_path)
                subclip.close()

                with open(output_file_path, 'rb') as output_file:
                    audio.file = ContentFile(output_file.read(), audio.file.name)

                # Set the size field before saving the model
                audio.size = audio.file.size  # Get the size of the processed file

            # Save the audio file using the appropriate storage
            try:
                audio.file.name = storage.save(audio.file.name, audio.file)
                audio.save()  # Save the audio instance with size and duration
                form.save_m2m()  # Save the ManyToMany relationships (tags, hashtags)
                logger.info(f"Audio file {audio.file.name} saved successfully for user {request.user.username}")
                return redirect('user_profile:voices', request.user.id)
            except Exception as e:
                logger.error(f"Error saving audio file {audio.file.name}: {e}")
                return render(request, 'upload_audio.html', {'form': form, 'error': str(e)})

        else:
            # If form is invalid, log and return errors to the template
            logger.warning("AudioForm is invalid.")
            logger.error(f"Form errors: {form.errors}")
            return redirect('user_profile:voices', request.user.id)

    else:
        # If GET request, simply render the form
        form = AudioForm()
        return render(request, 'upload_audio.html', {'form': form})




# View function
@login_required
def voices(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)

    # Fetch all audio uploads, ordered by creation date, for visibility and ownership checks
    audio_files = Audio.objects.filter(user=profile_user).order_by('-created_at')

    # Filter audio based on privacy and relationship to the requesting user
    filtered_audio = []
    for audio in audio_files:
        if audio.is_private and audio.user != request.user and not audio.tags.filter(id=request.user.id).exists():
            continue
        
        # Make usernames and URLs in the description clickable
        audio.description = make_usernames_clickable(audio.description)

        filtered_audio.append(audio)

    # Paginate the results, showing 100 audio files per page
    paginator = Paginator(filtered_audio, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the voices.html template and pass context
    return render(request, 'voices.html', {
        'page_obj': page_obj,
        'audio_count': Audio.objects.filter(user=profile_user).count(),
        'profile_user': profile_user,
    })




@login_required
def media_tags(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    tagged_media = Media.objects.filter(tags=profile_user).order_by('-created_at')
    paginator = Paginator(tagged_media, 30)  # Paginate the results
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'media_tags.html', {
        'profile_user': profile_user,
        'page_obj': page_obj,
    })


@login_required
@cache_control(private=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    is_authenticated = request.user.is_authenticated
    is_crawler = is_bot_request(request)

    # --- Basic stats (always public) ---
    followers_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()
    uploads_count = Media.objects.filter(user=profile_user).count()

    # --- Active story (within 24 hours) ---
    active_story = Story.objects.filter(
        user=profile_user,
        created_at__gt=timezone.now() - timezone.timedelta(hours=24)
    ).first()

    # --- Base queryset ---
    media_qs = Media.objects.filter(user=profile_user).order_by('-created_at')
    if active_story:
        media_qs = media_qs.exclude(id=active_story.media.id)

    media = media_qs.only('id', 'thumbnail', 'description', 'is_private')

    for item in media:
        item.description = linkify(item.description)

    # --- Default flags ---
    is_blocked = False
    is_blocked_by_profile_user = False
    is_following = False
    is_buddy = False

    # --- Authenticated logic ---
    if is_authenticated:
        is_blocked = BlockedUser.objects.filter(
            blocker=request.user, blocked=profile_user
        ).exists()

        is_blocked_by_profile_user = BlockedUser.objects.filter(
            blocker=profile_user, blocked=request.user
        ).exists()

        is_following = Follow.objects.filter(
            follower=request.user, following=profile_user
        ).exists()

        is_buddy = Buddy.objects.filter(
            user=profile_user, buddy=request.user
        ).exists()

        if is_blocked_by_profile_user:
            return render(request, 'user_not_found.html')

    # --- BOT / CRAWLER REQUEST ---
    if is_crawler:
        # Only expose public information for SEO/link previews
        public_media = [m for m in media if not m.is_private]
        preview_media = public_media[0] if public_media else None

        description = (
            f"Profile of {profile_user.username} on Socyfie — "
            f"{uploads_count} uploads, {followers_count} followers."
        )

        return bot_meta_response("meta_preview.html", {
            "title": f"{profile_user.username} on Socyfie",
            "description": description,
            "image_url": preview_media.thumbnail.url if preview_media and preview_media.thumbnail else "",
            "url": request.build_absolute_uri(),
            "media": preview_media,
            "profile_user": profile_user,
        })

    # --- GUEST (UNAUTHENTICATED) USERS ---
    if not is_authenticated:
        public_media = [m for m in media if not m.is_private]

        # If profile itself is private → show no media
        if profile_user.profile.is_private:
            return render(request, 'profile.html', {
                'profile_user': profile_user,
                'followers_count': followers_count,
                'following_count': following_count,
                'uploads_count': uploads_count,
                'is_following': False,
                'is_buddy': False,
                'is_blocked': False,
                'private_media': [],
            })

        paginator = Paginator(public_media, 9)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        return render(request, 'profile.html', {
            'profile_user': profile_user,
            'page_obj': page_obj,
            'followers_count': followers_count,
            'following_count': following_count,
            'uploads_count': uploads_count,
            'is_following': False,
            'is_buddy': False,
            'active_story': active_story,
            'is_blocked': False,
        })

    # --- AUTHENTICATED USERS (FULL ACCESS RULES) ---
    filtered_media = [
        m for m in media
        if not m.is_private or is_buddy or request.user == profile_user
    ]

    paginator = Paginator(filtered_media, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # If profile is private and viewer not permitted
    if (
        profile_user.profile.is_private
        and not is_following
        and not is_buddy
        and request.user != profile_user
    ):
        return render(request, 'profile.html', {
            'profile_user': profile_user,
            'followers_count': followers_count,
            'following_count': following_count,
            'uploads_count': uploads_count,
            'is_following': is_following,
            'is_buddy': is_buddy,
            'is_blocked': is_blocked,
            'private_media': [],
        })

    # --- Final profile render ---
    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'page_obj': page_obj,
        'followers_count': followers_count,
        'following_count': following_count,
        'uploads_count': uploads_count,
        'is_following': is_following,
        'is_buddy': is_buddy,
        'active_story': active_story,
        'is_blocked': is_blocked,
    })

#------------------------------------------
#
#follow function setup for letting users follow each other
#
#__________________________________________

#this funciton model worked purely for non ajax setup
'''
@login_required
def follow_user(request, user_id):
    user_to_follow = get_object_or_404(AuthUser, id=user_id)
    follow, created = Follow.objects.get_or_create(follower=request.user, following=user_to_follow)
    if created:
        Notification.objects.create(
            user=user_to_follow,
            content=f'{request.user.username} started following you.',
            type='follow',
            related_user=request.user
        )
    else:
        follow.delete()
        return redirect('user_profile:profile', user_id=user_id)
    return redirect('user_profile:profile', user_id=user_id)
'''

#this funciton model worked purely for ajax setup
'''
@login_required
def follow_user(request, user_id):
    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    user_to_follow = get_object_or_404(AuthUser, id=user_id)

    # Prevent self-follow
    if request.user == user_to_follow:
        return JsonResponse({"success": False, "error": "Cannot follow yourself"}, status=400)

    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )

    if created:
        Notification.objects.create(
            user=user_to_follow,
            content=f"{request.user.username} started following you.",
            type="follow",
            related_user=request.user
        )

        return JsonResponse({
            "success": True,
            "following": True
        })

    else:
        follow.delete()
        return JsonResponse({
            "success": True,
            "following": False
        })
'''
#this function model is hybrid and  worked for both ajax and non ajax setup
@login_required
def follow_user(request, user_id):

    is_ajax = request.headers.get("Accept") == "application/json" or \
              request.headers.get("x-requested-with") == "XMLHttpRequest"

    if request.method != "POST":
        if is_ajax:
            return JsonResponse({"success": False}, status=405)
        return redirect("user_profile:profile", user_id=user_id)

    user_to_follow = get_object_or_404(AuthUser, id=user_id)

    if request.user == user_to_follow:
        if is_ajax:
            return JsonResponse({"success": False, "error": "Cannot follow yourself"}, status=400)
        return redirect("user_profile:profile", user_id=user_id)

    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )

    if created:
        Notification.objects.create(
            user=user_to_follow,
            content=f"{request.user.username} started following you.",
            type="follow",
            related_user=request.user
        )
        following = True
    else:
        follow.delete()
        following = False

    #  AJAX → PURE JSON (like your original working version)
    if is_ajax:
        return JsonResponse({
            "success": True,
            "following": following
        })

    #  Normal browser submit → redirect
    return redirect("user_profile:profile", user_id=user_id)

#------------------------------------------
#
#follow function setup for letting users follow each other
#
#__________________________________________



@login_required
def unfollow_user(request, user_id):
    user_to_unfollow = get_object_or_404(AuthUser, id=user_id)
    follow = Follow.objects.filter(follower=request.user, following=user_to_unfollow).first()

    if follow:
        follow.delete()
        action = 'unfollowed'
    else:
        action = 'error'

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': action})

    return redirect('user_profile:profile', user_id=user_id)


@login_required
def remove_follower(request, user_id):
    # Get the user who is currently following the logged-in user
    follower_to_remove = get_object_or_404(AuthUser, id=user_id)

    # Find the Follow relationship where the current user is being followed by the follower_to_remove
    follow = Follow.objects.filter(follower=follower_to_remove, following=request.user).first()

    if follow:
        # Remove the follower
        follow.delete()
        action = 'removed'
    else:
        action = 'error'

    # Check if the request is an AJAX request
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': action})

    # Redirect back to the profile page of the current user
    return redirect('notion:followers_list', user_id=request.user.id)



@login_required
def tag_user_search(request):
    query = request.GET.get('q', '')
    users = AuthUser.objects.filter(
        Q(username__icontains=query)
    ).distinct()

    # Check if the request is an AJAX request
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        results = []
        for user in users:
            user_json = {
                'id': user.id,
                'text': user.username  # 'text' is the key expected by Select2
            }
            results.append(user_json)
        return JsonResponse({'results': results}, safe=False)

    return JsonResponse({'results': []}, safe=False)


#____________________________________________________________________________
# ENHANCED EXPLORE VIEW - INTEGRATED WITH COLLABORATIVE FILTERING
#____________________________________________________________________________


@login_required
#@cache_page(60 * 4)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def explore_me(request):
    """
    Enhanced explore with collaborative filtering and penalty system
    
    Features:
    - Collaborative filtering recommendations from Redis
    - Penalty system (creator/category/similar)
    - Hard filtering for heavily penalized creators
    - Profile category boost with time decay
    - Category exposure tracking and saturation prevention
    - Privacy-aware filtering
    - Served IDs caching (no duplicates in session)
    - Fallback mechanism
    """
    user = request.user
    redis_conn = get_redis_connection("default")
    now_ts = timezone.now()
    
    # ✅ Reset functionality
    if request.GET.get('reset') == '1':
        request.session.pop('explore_state', None)
        pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        pref.viewed_media = []
        pref.save()
        cache.delete(f'user_{user.id}_explore_served_ids')
        
        # Clear Redis tracking
        try:
            redis_conn.delete(f"user:category_exposure:{user.id}")
        except:
            pass
        
        return redirect('user_profile:explore_me')
    
    # ✅ User preferences
    pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
    liked_ht = pref.liked_hashtags or []
    not_int_ht = pref.not_interested_hashtags or []
    viewed_ht = pref.viewed_hashtags or []
    search_ht = pref.search_hashtags or []
    viewed_media_ids = set(pref.viewed_media or [])
    not_int_media_ids = set(pref.not_interested_media or [])
    liked_cats = pref.liked_categories or []
    
    hashtag_filter = request.GET.get('hashtag', '')
    q_filter = request.GET.get('q', '')
    
    # ✅ Load penalties from Redis
    creator_penalty_map = {}
    category_penalty_map = {}
    similar_ni_media = set()
    heavily_penalized_creators = set()
    category_exposure_count = {}
    
    try:
        # Creator penalties
        creator_penalties = redis_conn.zrange(
            f"user:creator_penalty:{user.id}", 
            0, -1, 
            withscores=True
        )
        creator_penalty_map = {
            int(cid.decode()): count for cid, count in creator_penalties
        }
        
        # Heavily penalized creators (3+ penalties = hard filter)
        heavily_penalized_creators = {
            int(cid.decode()) for cid, count in creator_penalties if count >= 3
        }
        
        # Category penalties
        category_penalties = redis_conn.zrange(
            f"user:category_penalty:{user.id}", 
            0, -1, 
            withscores=True
        )
        category_penalty_map = {
            cat.decode(): count for cat, count in category_penalties
        }
        
        # Similar media penalties
        similar_ni_media = set(
            int(mid.decode()) for mid in redis_conn.zrange(
                f"user:similar_ni:{user.id}", 
                0, -1
            )
        )
        
        # Category exposure (saturation tracking)
        exposure_key = f"user:category_exposure:{user.id}"
        category_exposures = redis_conn.zrange(
            exposure_key, 
            0, -1, 
            withscores=True
        )
        for cat_bytes, timestamp in category_exposures:
            category = cat_bytes.decode()
            category_exposure_count[category] = category_exposure_count.get(category, 0) + 1
        
        logger.debug(
            f"Loaded penalties for user {user.id}: "
            f"{len(creator_penalty_map)} creator, "
            f"{len(heavily_penalized_creators)} heavily penalized, "
            f"{len(category_penalty_map)} category, "
            f"{len(similar_ni_media)} similar, "
            f"exposures={category_exposure_count}"
        )
    except Exception as e:
        logger.warning(f"Failed to load penalties: {e}")
    
    # ✅ Get profile category
    profile_category = None
    try:
        profile_category = user.profile.category
    except:
        pass
    
    # ✅ Blocked users
    blocked_me = list(
        BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    )
    i_blocked = list(
        BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)
    )
    all_blocked = set(blocked_me) | set(i_blocked)
    
    # ✅ Served IDs from cache (session-level deduplication)
    served_cache_key = f'user_{user.id}_explore_served_ids'
    already_served_ids = set(cache.get(served_cache_key, []))
    
    # ✅ Get collaborative filtering recommendations from Redis
    personalized_media_ids = []
    personalized_scores_map = {}
    
    try:
        recommendation_key = f"user:reco:{user.id}"
        recommended_raw = redis_conn.zrevrange(
            recommendation_key,
            0,
            PERSONALIZED_POOL_SIZE * 2 - 1,  # Get more, filter later
            withscores=True
        )
        
        for mid, score in recommended_raw:
            mid_int = int(mid)
            if (mid_int not in already_served_ids and 
                mid_int not in not_int_media_ids and
                mid_int not in similar_ni_media):
                personalized_media_ids.append(mid_int)
                personalized_scores_map[mid_int] = score
        
        personalized_media_ids = personalized_media_ids[:PERSONALIZED_POOL_SIZE]
        
        logger.info(
            f"User {user.id} has {len(personalized_media_ids)} personalized recommendations"
        )
    except Exception as e:
        logger.warning(f"Failed to get recommendations: {e}")
    
    # ✅ Privacy filter (buddies + followers)
    users_who_buddied_me = set(
        Buddy.objects.filter(buddy=user).values_list('user', flat=True)
    )
    
    privacy_filter = (
        Q(is_private=False, user__profile__is_private=False) |
        Q(is_private=True, user__in=users_who_buddied_me) |
        Q(is_private=True, user=user)
    )
    
    # ✅ Fetch personalized media from DB
    personalized_media = []
    if personalized_media_ids:
        personalized_qs = Media.objects.filter(
            id__in=personalized_media_ids
        ).filter(
            privacy_filter
        ).exclude(
            user__in=all_blocked
        ).exclude(
            user__in=heavily_penalized_creators  # Hard filter
        ).select_related(
            'user', 'user__profile'
        ).prefetch_related('hashtags', 'likes')
        
        personalized_media = list(personalized_qs)
    
    # ✅ Category-based query (for diversity)
    base_qs = Media.objects.filter(
        privacy_filter
    ).exclude(
        user__in=all_blocked
    ).exclude(
        user__in=heavily_penalized_creators  # Hard filter
    ).exclude(
        id__in=already_served_ids
    ).exclude(
        id__in=not_int_media_ids
    ).exclude(
        id__in=similar_ni_media
    ).exclude(
        id__in=[m.id for m in personalized_media]  # Exclude personalized
    ).order_by('-created_at')
    
    # Apply filters
    if hashtag_filter:
        base_qs = base_qs.filter(hashtags__name__icontains=hashtag_filter)
    if q_filter:
        base_qs = base_qs.filter(
            Q(description__icontains=q_filter) | 
            Q(hashtags__name__icontains=q_filter)
        ).distinct()
    
    # Get category pool
    category_media_ids = list(
        base_qs.values_list('id', flat=True)[:CATEGORY_POOL_SIZE]
    )
    
    category_media_objs = Media.objects.filter(
        id__in=category_media_ids
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related('hashtags', 'likes')
    
    category_media_map = {m.id: m for m in category_media_objs}
    category_media = [
        category_media_map[mid] for mid in category_media_ids 
        if mid in category_media_map
    ]
    
    # ✅ Enhanced scoring function
    def enhanced_score(media, is_personalized=False):
        score = 0
        
        # 1. Collaborative filtering score (HIGH WEIGHT for personalized)
        if is_personalized and media.id in personalized_scores_map:
            score += personalized_scores_map[media.id] * 20
        
        # 2. Base score from calculate_media_score
        base_score = calculate_media_score(
            media,
            liked_ht,
            not_int_ht,
            viewed_ht,
            search_ht,
            liked_cats,
        )
        score += base_score
        
        # 3. Freshness boost
        age_hours = (now_ts - media.created_at).total_seconds() / 3600
        freshness_score = max(FRESHNESS_WEIGHT - (age_hours * DIVERSITY_DECAY_RATE), 0)
        score += freshness_score
        
        # 4. Profile category boost with time decay & saturation
        media_category = str(getattr(media, 'category', ''))
        if media_category and profile_category and media_category == profile_category:
            category_boost = 25 if is_personalized else 20
            
            # Time decay
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            category_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = category_exposure_count.get(media_category, 0)
            if exposure_count > 5:
                saturation_factor = max(0.2, 1 - (exposure_count - 5) * 0.1)
                category_boost *= saturation_factor
            
            score += category_boost
        
        # 5. Liked categories boost
        if media_category in liked_cats:
            liked_cat_boost = 15 if is_personalized else 12
            
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            liked_cat_boost *= time_decay_factor
            
            exposure_count = category_exposure_count.get(media_category, 0)
            if exposure_count > 8:
                saturation_factor = max(0.3, 1 - (exposure_count - 8) * 0.08)
                liked_cat_boost *= saturation_factor
            
            score += liked_cat_boost
        
        # 6. Diversity bonus (fresh categories)
        exposure_count = category_exposure_count.get(media_category, 0)
        if exposure_count == 0:
            score += 10
        
        # 7. Penalize own media
        if media.user_id == user.id:
            score -= 100
        
        # ✅ 8. APPLY PENALTIES
        penalty_multiplier = 2.0
        
        # Creator penalty
        creator_id = media.user_id
        if creator_id in creator_penalty_map:
            penalty_count = creator_penalty_map[creator_id]
            from .tasks import PENALTY_SAME_CREATOR
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            #creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count / 2, 2)

            penalty_multiplier *= creator_penalty
        
        # Category penalty
        if media_category in category_penalty_map:
            penalty_count = category_penalty_map[media_category]
            from .tasks import PENALTY_SAME_CATEGORY
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
        
        # Apply combined penalty
        score *= penalty_multiplier
        
        return score
    
    # ✅ Score all media
    scored_personalized = [
        (m, enhanced_score(m, is_personalized=True)) 
        for m in personalized_media
    ]
    
    scored_category = [
        (m, enhanced_score(m, is_personalized=False)) 
        for m in category_media
    ]
    
    # Combine: personalized first, then by score
    all_scored = scored_personalized + scored_category
    
    # ✅ Separate new vs viewed
    new_media = [(m, s) for m, s in all_scored if m.id not in viewed_media_ids]
    old_media = [(m, s) for m, s in all_scored if m.id in viewed_media_ids]
    
    # Add scoring noise and sort
    def noisy_score(item):
        return item[1] + random.uniform(-SCORING_NOISE, SCORING_NOISE)
    
    scored_new = sorted(new_media, key=noisy_score, reverse=True)
    scored_old = sorted(old_media, key=noisy_score, reverse=True)
    
    # Extract media objects
    sorted_media = [m for m, _ in scored_new] + [m for m, _ in scored_old]
    
    # ✅ Fallback mechanism
    if len(sorted_media) < 12:
        fallback = Media.objects.filter(
            privacy_filter
        ).exclude(
            id__in=not_int_media_ids.union({m.id for m in sorted_media})
        ).exclude(
            user__in=all_blocked
        ).exclude(
            user__in=heavily_penalized_creators
        ).annotate(
            likes_count=Count('likes')
        ).order_by('-likes_count', '-created_at')[:FALLBACK_MEDIA_COUNT]
        
        sorted_media += list(fallback)
        logger.info(f"Added {len(fallback)} fallback media for user {user.id}")
    
    # ✅ Pagination
    paginator = Paginator(sorted_media, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # ✅ Update served IDs cache
    served_this_page = [media.id for media in page_obj]
    updated_served_ids = list(already_served_ids.union(served_this_page))
    cache.set(served_cache_key, updated_served_ids, timeout=60 * 30)
    
    # ✅ Track category exposure in Redis
    try:
        now_timestamp = int(time.time())
        exposure_key = f"user:category_exposure:{user.id}"
        
        for media in page_obj:
            category = getattr(media, 'category', None)
            if category:
                redis_conn.zadd(exposure_key, {category: now_timestamp})
        
        # Remove old exposures (older than 1 hour)
        one_hour_ago = now_timestamp - 3600
        redis_conn.zremrangebyscore(exposure_key, 0, one_hour_ago)
        redis_conn.expire(exposure_key, 60 * 60 * 2)
    except Exception as e:
        logger.warning(f"Category exposure tracking failed: {e}")
    
    # ✅ AJAX response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_json = []
        for m in page_obj:
            media_json.append({
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.lower().endswith(
                    ('.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv')
                ),
                'thumbnail_url': m.thumbnail.url if m.thumbnail else None,
                'explore_detail_url': reverse('user_profile:explore_detail', args=[m.id]),
            })
        
        return JsonResponse({
            'media': media_json,
            'has_next': page_obj.has_next(),
            'current_page': page_obj.number,
        }, headers={'Cache-Control': 'public, max-age=120, s-maxage=120'})
    
    # ✅ Initial render
    return render(request, 'explore.html', {
        'page_obj': page_obj,
        'hashtag_filter': hashtag_filter,
        'q_filter': q_filter,
    })

#____________________________________________________________________________
# ENHANCED EXPLORE VIEW - INTEGRATED WITH COLLABORATIVE FILTERING
#____________________________________________________________________________



# ===============================================================
# ENHANCED UPLOAD SEARCH WITH COLLABORATIVE FILTERING & PENALTIES
# ===============================================================
 
@login_required
def search_uploads(request):
    """
    Enhanced upload search with collaborative filtering and penalty system
    
    Features:
    - Integrates with collaborative filtering recommendations
    - Applies penalty system (creator/category/similar)
    - Privacy-aware filtering
    - Profile category boost
    - Saturation prevention
    - Fresh, personalized results (no random shuffle)
    """
    query = request.GET.get('q', '').strip()
    hashtag_filter = request.GET.get('hashtag', '').strip()
    redis_conn = get_redis_connection("default")
    now_ts = timezone.now()
    
    # ✅ Fetch user preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(
        user=request.user
    )
    
    liked_hashtags = user_hashtag_pref.liked_hashtags or []
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags or []
    viewed_hashtags = user_hashtag_pref.viewed_hashtags or []
    search_hashtags = user_hashtag_pref.search_hashtags or []
    viewed_media = user_hashtag_pref.viewed_media or []
    liked_categories = user_hashtag_pref.liked_categories or []
    not_interested_media_ids = set(user_hashtag_pref.not_interested_media or [])
    
    # ✅ Track search query
    if query:
        user_hashtag_pref.add_search_hashtag(query)
        
        # Track in Redis for collaborative filtering
        try:
            search_key = f"user:search:media:{request.user.id}"
            now_timestamp = int(time.time())
            redis_conn.zadd(search_key, {query.lower(): now_timestamp})
            redis_conn.expire(search_key, 60 * 60 * 24 * 30)  # 30 days
        except Exception as e:
            logger.warning(f"Failed to track media search: {e}")
    
    # ✅ Load penalties from Redis
    creator_penalty_map = {}
    category_penalty_map = {}
    similar_ni_media = set()
    heavily_penalized_creators = set()
    category_exposure_count = {}
    
    try:
        # Creator penalties
        creator_penalties = redis_conn.zrange(
            f"user:creator_penalty:{request.user.id}", 
            0, -1, 
            withscores=True
        )
        creator_penalty_map = {
            int(cid.decode()): count for cid, count in creator_penalties
        }
        
        # Heavily penalized creators (3+ penalties = filter out)
        heavily_penalized_creators = {
            int(cid.decode()) for cid, count in creator_penalties if count >= 3
        }
        
        # Category penalties
        category_penalties = redis_conn.zrange(
            f"user:category_penalty:{request.user.id}", 
            0, -1, 
            withscores=True
        )
        category_penalty_map = {
            cat.decode(): count for cat, count in category_penalties
        }
        
        # Similar media penalties
        similar_ni_media = set(
            int(mid.decode()) for mid in redis_conn.zrange(
                f"user:similar_ni:{request.user.id}", 
                0, -1
            )
        )
        
        # Category exposure (saturation tracking)
        exposure_key = f"user:category_exposure:{request.user.id}"
        category_exposures = redis_conn.zrange(
            exposure_key, 
            0, -1, 
            withscores=True
        )
        for cat_bytes, timestamp in category_exposures:
            category = cat_bytes.decode()
            category_exposure_count[category] = category_exposure_count.get(category, 0) + 1
    except Exception as e:
        logger.warning(f"Failed to load penalties: {e}")
    
    # ✅ Get profile category for boost
    profile_category = None
    try:
        profile_category = request.user.profile.category
    except:
        pass
    
    # ✅ Exclude blocked users
    blocked_users = BlockedUser.objects.filter(
        blocker=request.user
    ).values_list('blocked', flat=True)
    
    blocked_by_users = BlockedUser.objects.filter(
        blocked=request.user
    ).values_list('blocker', flat=True)
    
    all_blocked = set(blocked_users) | set(blocked_by_users)
    
    # ✅ Privacy filter (includes buddies and followers)
    users_who_buddied_me = set(
        Buddy.objects.filter(buddy=request.user).values_list('user', flat=True)
    )
    
    privacy_filter = (
        Q(is_private=False, user__profile__is_private=False) |
        Q(is_private=True, user__in=users_who_buddied_me) |
        Q(is_private=True, user=request.user)
    )
    
    # ✅ Base queryset with eager loading
    media_objects = (
        Media.objects.filter(privacy_filter)
        .exclude(user__in=all_blocked)
        .exclude(user__in=heavily_penalized_creators)  # Hard filter
        .exclude(id__in=not_interested_media_ids)
        .exclude(id__in=similar_ni_media)
        .select_related("user", "user__profile")
        .prefetch_related("hashtags", "likes")
    )
    
    # ✅ Apply search filters
    if query:
        media_objects = media_objects.filter(
            Q(description__icontains=query) |
            Q(hashtags__name__icontains=query) |
            Q(user__username__icontains=query)
        )
    
    if hashtag_filter:
        media_objects = media_objects.filter(
            hashtags__name__icontains=hashtag_filter
        )
    
    media_objects = media_objects.distinct()
    
    # ✅ Get collaborative filtering recommendations
    personalized_scores = {}
    try:
        recommendation_key = f"user:reco:{request.user.id}"
        recommended_raw = redis_conn.zrevrange(
            recommendation_key,
            0,
            999,
            withscores=True
        )
        
        for mid, score in recommended_raw:
            personalized_scores[int(mid)] = score
    except Exception as e:
        logger.warning(f"Failed to get recommendations: {e}")
    
    # ✅ Convert to list for scoring (NO RANDOM SHUFFLE)
    media_list = list(media_objects[:500])  # Limit for performance
    
    # ✅ Score each media with ENHANCED algorithm
    scored_media = []
    for media in media_list:
        score = 0
        
        # 1. Collaborative filtering score (HIGH WEIGHT)
        if media.id in personalized_scores:
            score += personalized_scores[media.id] * 15
        
        # 2. Freshness boost
        days_old = (now_ts - media.created_at).days
        freshness_score = max(0, 30 - days_old)
        score += freshness_score * 2
        
        # 3. Query relevance boost
        if query:
            # Exact hashtag match
            media_hashtags = [h.name.lower() for h in media.hashtags.all()]
            if query.lower() in media_hashtags:
                score += 50
            
            # Description match
            if media.description and query.lower() in media.description.lower():
                # Word count in description
                word_count = media.description.lower().count(query.lower())
                score += 20 * min(word_count, 3)
            
            # Username match
            if query.lower() in media.user.username.lower():
                score += 15
        
        # 4. Liked hashtags boost
        media_hashtags = [h.name.lower() for h in media.hashtags.all()]
        liked_overlap = set(media_hashtags) & set(h.lower() for h in liked_hashtags)
        score += len(liked_overlap) * 10
        
        # 5. Profile category boost with time decay & saturation
        media_category = str(getattr(media, 'category', ''))
        if media_category and profile_category and media_category == profile_category:
            category_boost = 30
            
            # Time decay
            age_hours = (now_ts - media.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            category_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = category_exposure_count.get(media_category, 0)
            if exposure_count > 5:
                saturation_factor = max(0.2, 1 - (exposure_count - 5) * 0.1)
                category_boost *= saturation_factor
            
            score += category_boost
        
        # 6. Liked categories boost
        if media_category in liked_categories:
            liked_cat_boost = 20
            
            age_hours = (now_ts - media.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            liked_cat_boost *= time_decay_factor
            
            exposure_count = category_exposure_count.get(media_category, 0)
            if exposure_count > 8:
                saturation_factor = max(0.3, 1 - (exposure_count - 8) * 0.08)
                liked_cat_boost *= saturation_factor
            
            score += liked_cat_boost
        
        # 7. Diversity bonus (fresh categories)
        exposure_count = category_exposure_count.get(media_category, 0)
        if exposure_count == 0:
            score += 12
        
        # 8. Engagement boost
        score += media.likes.count() * 0.5
        score += media.comments.count() * 0.8
        
        # 9. NOT INTERESTED hashtags penalty
        not_interested_overlap = set(media_hashtags) & set(
            h.lower() for h in not_interested_hashtags
        )
        score -= len(not_interested_overlap) * 15
        
        # ✅ 10. APPLY PENALTIES
        penalty_multiplier = 2.0
        
        # Creator penalty
        creator_id = media.user_id
        if creator_id in creator_penalty_map:
            penalty_count = creator_penalty_map[creator_id]
            from .tasks import PENALTY_SAME_CREATOR
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            #creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count / 2, 2)

            penalty_multiplier *= creator_penalty
        
        # Category penalty
        if media_category in category_penalty_map:
            penalty_count = category_penalty_map[media_category]
            from .tasks import PENALTY_SAME_CATEGORY
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
        
        # Apply combined penalty
        score *= penalty_multiplier
        
        scored_media.append((media, score))
    
    # ✅ Sort by score (NO random shuffle - fully personalized)
    scored_media.sort(key=lambda x: x[1], reverse=True)
    sorted_media = [m for m, _ in scored_media]
    
    # ✅ Pagination
    paginator = Paginator(sorted_media, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    # ✅ Update viewed media
    new_viewed = set(viewed_media)
    for media in page_obj:
        if media.id not in new_viewed:
            new_viewed.add(media.id)
    
    user_hashtag_pref.viewed_media = list(new_viewed)[-100:]  # Keep last 100
    user_hashtag_pref.save(update_fields=["viewed_media"])
    
    # ✅ Track category exposure
    try:
        now_timestamp = int(time.time())
        exposure_key = f"user:category_exposure:{request.user.id}"
        
        for media in page_obj:
            category = getattr(media, 'category', None)
            if category:
                redis_conn.zadd(exposure_key, {category: now_timestamp})
        
        # Remove old exposures
        one_hour_ago = now_timestamp - 3600
        redis_conn.zremrangebyscore(exposure_key, 0, one_hour_ago)
        redis_conn.expire(exposure_key, 60 * 60 * 2)
    except Exception as e:
        logger.warning(f"Category exposure tracking failed: {e}")
    
    # ✅ AJAX response
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        media_list = [
            {
                "id": m.id,
                "file_url": m.file.url,
                "thumbnail_url": m.thumbnail.url if hasattr(m, 'thumbnail') and m.thumbnail else m.file.url,
                "is_video": m.file.url.lower().endswith(".mp4"),
                "user_username": m.user.username,
                "user_id": m.user.id,
                "description": m.description,
                "likes_count": m.likes.count(),
                "is_liked": request.user in m.likes.all(),
            }
            for m in page_obj
        ]
        return JsonResponse({"media": media_list, "has_next": page_obj.has_next()})
    
    return render(request, "explore.html", {
        "page_obj": page_obj,
        "query": query,
        "hashtag_filter": hashtag_filter,
    })



# ===============================================================
# ENHANCED UPLOAD SEARCH WITH COLLABORATIVE FILTERING & PENALTIES
# ===============================================================


#___________________________________________________________
#explore detail function implementing new upgrades of trending and batch dispacther to it
#
#___________________________________________________________

'''
SESSION_SEEN_RELATED_LIMIT = 200  # Max related media IDs to track per session
RELATED_MEDIA_FETCH_MULTIPLIER = 3  # Fetch 3x more candidates for better rotation
PERSONALIZED_RELATED_LIMIT = 20  # Limit for personalized related media

'''

RELATED_MEDIA_FETCH_MULTIPLIER = 2
PERSONALIZED_RELATED_LIMIT = 20
SESSION_SEEN_RELATED_LIMIT = 40  # Max related media IDs to track per session
#PAGE_SIZE = 8
# Constants
#CATEGORY_ENGAGEMENT_WEIGHT = 13
#FRESHNESS_WEIGHT = 10

# CURSOR-BASED INFINITE SCROLL explore_detail WITH FULL INTEGRATION

def explore_detail(request, media_id):
    """
    Media detail view with cursor-based infinite scroll
    
    Features:
    - Redis-based persistent seen tracking
    - Collaborative filtering integration
    - Not interested filtering
    - Privacy-aware
    - Cursor pagination
    -  NEW: Penalty system (creator/category/similar)
    -  NEW: Profile category boost with time decay
    -  NEW: Saturation prevention
    -  NEW: Hard filter for heavily penalized creators
    """
    
    media = get_object_or_404(Media, id=media_id)
    user = media.user
    user_id = getattr(request.user, "pk", None)
    now_ts = timezone.now()
    
    # --------------------------------------------------
    # REDIS CONNECTION & ACTIVE USER TRACKING
    # --------------------------------------------------
    redis_conn = get_redis_connection("default")
    
    if user_id:
        try:
            now_timestamp = int(time.time())
            cutoff = now_timestamp - 3600
            
            # Mark user as active
            redis_conn.zadd("active:users", {user_id: now_timestamp})
            redis_conn.zremrangebyscore("active:users", 0, cutoff)
        except Exception as e:
            logger.warning(f"Active user tracking failed: {e}")
    
    # --------------------------------------------------
    # BLOCK & PRIVACY CHECKS
    # --------------------------------------------------
    if user_id:
        is_blocked_by_media_owner = BlockedUser.objects.filter(
            blocker=user, blocked_id=user_id
        ).exists()
        
        has_blocked_media_owner = BlockedUser.objects.filter(
            blocker_id=user_id, blocked=user
        ).exists()
        
        if is_blocked_by_media_owner:
            return render(request, 'user_not_found.html')
        
        is_following = Follow.objects.filter(
            follower_id=user_id, following=user
        ).exists()
        
        is_buddy = Buddy.objects.filter(
            user=user, buddy_id=user_id
        ).exists()
        
        # Restrict private content
        if (media.is_private or user.profile.is_private):
            if not is_buddy and not is_following and request.user != user:
                return render(request, 'private_upload.html')
    else:
        is_blocked_by_media_owner = False
        has_blocked_media_owner = False
        is_following = False
        is_buddy = False
    
    # --------------------------------------------------
    # GET REDIS CACHED SEEN RELATED MEDIA
    # --------------------------------------------------
    seen_related_ids = set()
    
    if user_id:
        try:
            cache_key = f"user:seen_related:{user_id}:media:{media_id}"
            cached_ids = redis_conn.smembers(cache_key)
            seen_related_ids = {int(sid) for sid in cached_ids}
            logger.info(f"User {user_id} has seen {len(seen_related_ids)} related for media {media_id}")
        except Exception as e:
            logger.warning(f"Error fetching cached seen related: {e}")
    
    # --------------------------------------------------
    # USER PREFERENCES & NOT INTERESTED
    # --------------------------------------------------
    not_interested_media_ids = set()
    user_hashtag_pref = None
    
    if user_id:
        user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user_id=user_id)
        
        # Track viewed media
        if media.id not in (user_hashtag_pref.viewed_media or []):
            viewed_media = user_hashtag_pref.viewed_media or []
            viewed_media.append(media.id)
            user_hashtag_pref.viewed_media = viewed_media[-60:]
            user_hashtag_pref.save(update_fields=["viewed_media"])
        
        # Track viewed hashtags
        description_hashtags = re.findall(r'#(\w+)', media.description or "")
        user_hashtag_pref.add_viewed_hashtag(description_hashtags)
        
        # Get not interested
        not_interested_media_ids = set(user_hashtag_pref.not_interested_media or [])
        
        # --------------------------------------------------
        # REDIS VIEW TRACKING (For Collaborative Filtering)
        # --------------------------------------------------
        try:
            now_timestamp = int(time.time())
            
            redis_conn.zadd(f"user:viewed:{user_id}", {media.id: now_timestamp})
            redis_conn.zadd(f"media:viewed_by:{media.id}", {user_id: now_timestamp})
            
            redis_conn.expire(f"user:viewed:{user_id}", 60 * 60 * 24 * 30)
            redis_conn.expire(f"media:viewed_by:{media.id}", 60 * 60 * 24 * 30)
        except Exception as e:
            logger.warning(f"Redis view tracking failed: {e}")
    
    # --------------------------------------------------
    #  NEW: LOAD PENALTIES & PROFILE CATEGORY DATA
    # --------------------------------------------------
    creator_penalty_map = {}
    category_penalty_map = {}
    similar_ni_media = set()
    profile_category = None
    category_exposure_count = {}
    heavily_penalized_creators = set()
    
    if user_id:
        try:
            # Load creator penalties
            creator_penalties = redis_conn.zrange(
                f"user:creator_penalty:{user_id}", 0, -1, withscores=True
            )
            creator_penalty_map = {
                int(cid.decode()): count for cid, count in creator_penalties
            }
            
            #  Load heavily penalized creators (3+ penalties = hard filter)
            heavily_penalized_creators = {
                int(cid.decode()) for cid, count in creator_penalties if count >= 3
            }
            
            # Load category penalties
            category_penalties = redis_conn.zrange(
                f"user:category_penalty:{user_id}", 0, -1, withscores=True
            )
            category_penalty_map = {
                cat.decode(): count for cat, count in category_penalties
            }
            
            # Load similar media penalties
            similar_ni_media = set(
                int(mid.decode()) for mid in redis_conn.zrange(
                    f"user:similar_ni:{user_id}", 0, -1
                )
            )
            
            # Load profile category
            try:
                profile_category = request.user.profile.category
            except:
                profile_category = None
            
            # Load category exposure (track saturation)
            exposure_key = f"user:category_exposure:{user_id}"
            category_exposures = redis_conn.zrange(
                exposure_key, 0, -1, withscores=True
            )
            for cat_bytes, timestamp in category_exposures:
                category = cat_bytes.decode()
                category_exposure_count[category] = category_exposure_count.get(category, 0) + 1
            
            logger.debug(
                f"Loaded penalties for user {user_id}: "
                f"{len(creator_penalty_map)} creator penalties, "
                f"{len(heavily_penalized_creators)} heavily penalized, "
                f"{len(category_penalty_map)} category penalties, "
                f"{len(similar_ni_media)} similar penalties, "
                f"profile_category={profile_category}, "
                f"exposures={category_exposure_count}"
            )
        except Exception as e:
            logger.warning(f"Failed to load penalty/category data: {e}")
    
    # --------------------------------------------------
    # FETCH PERSONALIZED RECOMMENDATIONS
    # --------------------------------------------------
    personalized_related_ids = []
    personalized_scores_map = {}
    
    if user_id:
        try:
            recommendation_key = f"user:reco:{user_id}"
            
            recommended_raw = redis_conn.zrevrange(
                recommendation_key,
                0,
                PERSONALIZED_RELATED_LIMIT * 2 - 1,
                withscores=True
            )
            
            for mid, score in recommended_raw:
                mid_int = int(mid)
                if mid_int not in seen_related_ids and mid_int != media_id:
                    personalized_related_ids.append(mid_int)
                    personalized_scores_map[mid_int] = score
            
            personalized_related_ids = personalized_related_ids[:PERSONALIZED_RELATED_LIMIT]
        except Exception as e:
            logger.warning(f"Error fetching personalized related: {e}")
    
    # --------------------------------------------------
    # BUILD PRIVACY FILTER
    # --------------------------------------------------
    users_who_buddied_me = set()
    if user_id:
        users_who_buddied_me = set(
            Buddy.objects.filter(buddy_id=user_id).values_list('user', flat=True)
        )

    # GET BLOCKED USERS
    users_i_blocked = set()
    users_who_blocked_me = set()

    if user_id:
        users_i_blocked = set(
            BlockedUser.objects.filter(blocker_id=user_id).values_list('blocked_id', flat=True)
        )
        users_who_blocked_me = set(
            BlockedUser.objects.filter(blocked_id=user_id).values_list('blocker_id', flat=True)
        )

    all_blocked_users = users_i_blocked | users_who_blocked_me

    
    if user_id:
        privacy_filter = (
            Q(is_private=False, user__profile__is_private=False) |
            Q(is_private=True, user__in=users_who_buddied_me) |
            Q(is_private=True, user_id=user_id)
        )
    else:
        privacy_filter = Q(is_private=False, user__profile__is_private=False)
    
    # --------------------------------------------------
    # FETCH PERSONALIZED RELATED FROM DB
    # --------------------------------------------------
    personalized_related_media = []
    if personalized_related_ids:
        personalized_qs = Media.objects.filter(
            id__in=personalized_related_ids
        ).filter(
            category=media.category  # Same category
        ).filter(
            privacy_filter
        ).exclude(
            id__in=not_interested_media_ids
        ).exclude(
            id__in=seen_related_ids
        ).exclude(
            user__in=all_blocked_users
        ).exclude(
            user__in=heavily_penalized_creators  #  NEW: Hard filter 3+ penalties
        ).select_related(
            'user', 'user__profile'
        ).prefetch_related('hashtags', 'likes')
        
        personalized_related_media = list(personalized_qs)
    
    # --------------------------------------------------
    # GET CURSOR FOR PAGINATION
    # --------------------------------------------------
    cursor = request.GET.get("cursor")
    cursor_id = int(cursor) if cursor else 0
    
    # --------------------------------------------------
    # FETCH CATEGORY-BASED RELATED MEDIA
    # --------------------------------------------------
    category_related_qs = Media.objects.filter(
        category=media.category
    ).exclude(
        id=media_id
    ).exclude(
        id__in=seen_related_ids
    ).exclude(
        id__in=not_interested_media_ids
    ).exclude(
        id__in=[m.id for m in personalized_related_media]  # Exclude personalized
    ).exclude(
        user__in=all_blocked_users
    ).exclude(
        user__in=heavily_penalized_creators  #  NEW: Hard filter 3+ penalties
    ).filter(
        privacy_filter
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related('hashtags', 'likes')
    
    # Apply cursor pagination
    if cursor_id:
        category_related_qs = category_related_qs.filter(id__gt=cursor_id)
    
    category_related_qs = category_related_qs.order_by('id')
    category_related_media = list(category_related_qs[:300])  # Get candidates
    
    # --------------------------------------------------
    # CHECK IF EXHAUSTED (RESET CACHE)
    # --------------------------------------------------
    total_available = len(personalized_related_media) + len(category_related_media)
    
    if total_available < PAGE_SIZE and len(seen_related_ids) > 0 and user_id:
        logger.info(f"Exhausted related for user {user_id}, media {media_id}. Resetting.")
        try:
            cache_key = f"user:seen_related:{user_id}:media:{media_id}"
            redis_conn.delete(cache_key)
            seen_related_ids = set()
            
            # Re-fetch with empty cache
            personalized_qs = Media.objects.filter(
                id__in=personalized_related_ids
            ).filter(category=media.category).filter(privacy_filter).exclude(
                id__in=not_interested_media_ids
            ).exclude(
                user__in=all_blocked_users
            ).exclude(
                user__in=heavily_penalized_creators  #  NEW
            ).select_related('user', 'user__profile').prefetch_related('hashtags', 'likes')
            personalized_related_media = list(personalized_qs)
            
            category_related_qs = Media.objects.filter(
                category=media.category
            ).exclude(id=media_id).exclude(
                id__in=not_interested_media_ids
            ).exclude(
                id__in=[m.id for m in personalized_related_media]
            ).exclude(
                user__in=all_blocked_users
            ).exclude(
                user__in=heavily_penalized_creators  #  NEW
            ).filter(privacy_filter).select_related(
                'user', 'user__profile'
            ).prefetch_related('hashtags', 'likes')
            
            if cursor_id:
                category_related_qs = category_related_qs.filter(id__gt=cursor_id)
            
            category_related_media = list(category_related_qs.order_by('id')[:300])
            total_available = len(personalized_related_media) + len(category_related_media)
        except Exception as e:
            logger.warning(f"Error resetting cache: {e}")
    
    # --------------------------------------------------
    #  ENHANCED SCORING WITH PENALTIES & PROFILE CATEGORY
    # --------------------------------------------------
    main_description_words = set(re.findall(r'\w+', (media.description or "").lower()))
    scored_media = []
    
    # Score personalized (higher priority)
    for m in personalized_related_media:
        score = 0
        
        # 1. Collaborative filtering score (high weight)
        redis_score = personalized_scores_map.get(m.id, 0)
        score += redis_score * 10
        
        # 2. Freshness
        if getattr(m, 'created_at', None):
            days_old = (now_ts - m.created_at).days
            freshness_score = max(0, FRESHNESS_WEIGHT - days_old)
            score += freshness_score * 2
        
        # 3. Description overlap
        desc = (m.description or "").lower()
        if desc:
            overlap = main_description_words & set(re.findall(r'\w+', desc))
            if overlap:
                score += 6 * len(overlap)
        
        #  4. NEW: Profile category boost with time decay & saturation
        media_category_str = str(getattr(m, 'category', ''))
        if media_category_str and profile_category and media_category_str == profile_category:
            category_boost = 25  # Gentle boost
            
            # Time decay (decay over 3 days)
            age_hours = (now_ts - m.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            category_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = category_exposure_count.get(media_category_str, 0)
            if exposure_count > 5:
                saturation_factor = max(0.2, 1 - (exposure_count - 5) * 0.1)
                category_boost *= saturation_factor
            
            score += category_boost
        
        #  5. NEW: Liked categories boost (from engagement history)
        if user_hashtag_pref and media_category_str in (user_hashtag_pref.liked_categories or []):
            liked_boost = 15
            
            # Time decay
            age_hours = (now_ts - m.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            liked_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = category_exposure_count.get(media_category_str, 0)
            if exposure_count > 8:
                saturation_factor = max(0.3, 1 - (exposure_count - 8) * 0.08)
                liked_boost *= saturation_factor
            
            score += liked_boost
        
        #  6. NEW: Diversity bonus (fresh categories)
        exposure_count = category_exposure_count.get(media_category_str, 0)
        if exposure_count == 0:
            score += 10  # Small bonus for variety
        
        #  7. NEW: Apply penalties
        penalty_multiplier = 2.0
        
        # Creator penalty
        creator_id = m.user_id
        if creator_id in creator_penalty_map:
            penalty_count = creator_penalty_map[creator_id]
            from .tasks import PENALTY_SAME_CREATOR
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            #creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count / 2, 2)

            penalty_multiplier *= creator_penalty
        
        # Category penalty
        if media_category_str in category_penalty_map:
            penalty_count = category_penalty_map[media_category_str]
            from .tasks import PENALTY_SAME_CATEGORY
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
        
        # Similar media penalty
        if m.id in similar_ni_media:
            from .tasks import PENALTY_SIMILAR_MEDIA
            penalty_multiplier *= PENALTY_SIMILAR_MEDIA
        
        # Apply combined penalty
        score *= penalty_multiplier
        
        scored_media.append((m, score, True))  # True = personalized
    
    # Score category-based
    for m in category_related_media:
        score = 0
        score += CATEGORY_ENGAGEMENT_WEIGHT
        
        # 1. Freshness
        if getattr(m, 'created_at', None):
            days_old = (now_ts - m.created_at).days
            freshness_score = max(0, FRESHNESS_WEIGHT - days_old)
            score += freshness_score
        
        # 2. Description overlap
        desc = (m.description or "").lower()
        if desc:
            overlap = main_description_words & set(re.findall(r'\w+', desc))
            if overlap:
                score += 6 * len(overlap)
        
        #  3. NEW: Profile category boost (slightly lower for category pool)
        media_category_str = str(getattr(m, 'category', ''))
        if media_category_str and profile_category and media_category_str == profile_category:
            category_boost = 20
            
            age_hours = (now_ts - m.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            category_boost *= time_decay_factor
            
            exposure_count = category_exposure_count.get(media_category_str, 0)
            if exposure_count > 5:
                saturation_factor = max(0.2, 1 - (exposure_count - 5) * 0.1)
                category_boost *= saturation_factor
            
            score += category_boost
        
        #  4. NEW: Liked categories boost
        if user_hashtag_pref and media_category_str in (user_hashtag_pref.liked_categories or []):
            liked_boost = 12
            
            age_hours = (now_ts - m.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            liked_boost *= time_decay_factor
            
            exposure_count = category_exposure_count.get(media_category_str, 0)
            if exposure_count > 8:
                saturation_factor = max(0.3, 1 - (exposure_count - 8) * 0.08)
                liked_boost *= saturation_factor
            
            score += liked_boost
        
        #  5. NEW: Diversity bonus
        exposure_count = category_exposure_count.get(media_category_str, 0)
        if exposure_count == 0:
            score += 8
        
        #  6. NEW: Apply penalties
        penalty_multiplier = 2.0
        
        creator_id = m.user_id
        if creator_id in creator_penalty_map:
            penalty_count = creator_penalty_map[creator_id]
            from .tasks import PENALTY_SAME_CREATOR
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            #creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count / 2, 2)

            penalty_multiplier *= creator_penalty
        
        if media_category_str in category_penalty_map:
            penalty_count = category_penalty_map[media_category_str]
            from .tasks import PENALTY_SAME_CATEGORY
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
        
        if m.id in similar_ni_media:
            from .tasks import PENALTY_SIMILAR_MEDIA
            penalty_multiplier *= PENALTY_SIMILAR_MEDIA
        
        score *= penalty_multiplier
        
        scored_media.append((m, score, False))  # False = category
    
    # Sort: personalized first, then by score
    scored_media.sort(key=lambda x: (not x[2], -x[1]))
    
    # Extract sorted media
    all_related_media = [m for m, _, _ in scored_media]

    # --------------------------------------------------
    # POSITION-BASED CURSOR PAGINATION (CORRECT FLOW)
    # --------------------------------------------------

    cursor = request.GET.get("cursor")
    cursor_id = int(cursor) if cursor else None

    start_index = 0

    if cursor_id:
        # Find position of cursor in full blended list
        for index, m in enumerate(all_related_media):
            if m.id == cursor_id:
                start_index = index + 1   # START AFTER selected media
                break

    # Slice from the correct position
    media_batch = all_related_media[start_index:start_index + PAGE_SIZE]

    # Determine next cursor
    next_cursor = None
    if media_batch:
        next_cursor = media_batch[-1].id

    # Check if more items exist after this batch
    has_more = start_index + PAGE_SIZE < len(all_related_media)


    # --------------------------------------------------
    # TRACK NEWLY SHOWN MEDIA IN REDIS
    # --------------------------------------------------
    page_related_ids = [m.id for m in media_batch]
    
    if page_related_ids and user_id:
        try:
            cache_key = f"user:seen_related:{user_id}:media:{media_id}"
            redis_conn.sadd(cache_key, *page_related_ids)
            redis_conn.expire(cache_key, 60 * 60 * 24 * 30)  # 30 days
            logger.info(f"Cached {len(page_related_ids)} related for user {user_id}, media {media_id}")
        except Exception as e:
            logger.warning(f"Error caching seen related: {e}")
    
    # --------------------------------------------------
    #  NEW: TRACK CATEGORY EXPOSURE (Saturation Prevention)
    # --------------------------------------------------
    if user_id and media_batch:
        try:
            now_timestamp = int(time.time())
            exposure_key = f"user:category_exposure:{user_id}"
            
            # Track each category seen in this batch
            for m in media_batch:
                category = getattr(m, 'category', None)
                if category:
                    redis_conn.zadd(exposure_key, {category: now_timestamp})
            
            # Remove old exposures (older than 1 hour)
            one_hour_ago = now_timestamp - 3600
            redis_conn.zremrangebyscore(exposure_key, 0, one_hour_ago)
            
            # Set expiry (2 hours)
            redis_conn.expire(exposure_key, 60 * 60 * 2)
        except Exception as e:
            logger.warning(f"Category exposure tracking failed: {e}")
    
    # --------------------------------------------------
    # TRACK UNIQUE VIEW (ONCE PER USER)
    # --------------------------------------------------
    if user_id:
        has_viewed = Engagement.objects.filter(
            user_id=user_id,
            media=media,
            engagement_type='view'
        ).exists()
        
        if not has_viewed:
            Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
            Engagement.objects.create(
                media=media,
                user_id=user_id,
                engagement_type='view'
            )
    else:
        # Anonymous: increment every time
        Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
    
    # --------------------------------------------------
    # AJAX RESPONSE (Infinite Scroll)
    # --------------------------------------------------
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        data = {
            "related_media": [
                {
                    "id": m.id,
                    "file_url": m.file.url,
                    "thumbnail_url": m.thumbnail.url if hasattr(m, 'thumbnail') and m.thumbnail else m.file.url,
                    "is_video": getattr(m, 'is_video', m.file.url.lower().endswith('.mp4')),
                    "likes_count": m.likes.count(),
                    "is_liked_by_user": request.user in m.likes.all() if user_id else False,
                    "user": {
                        "id": m.user.id,
                    },
                    "user_username": m.user.username,

                    "explore_detail_url": reverse("user_profile:explore_detail", kwargs={"media_id": m.id}),
                    "like_url": reverse( "user_profile:like_media", kwargs={"media_id": m.id}),

                    "profile_url": reverse( "user_profile:profile", kwargs={"user_id": m.user.id}),

                    "csrf_token": request.COOKIES.get("csrftoken"),
                }
                for m in media_batch
            ],
            "next_cursor": next_cursor,
            "has_more": has_more
        }
        return JsonResponse(data)
    
    # --------------------------------------------------
    # NORMAL PAGE LOAD
    # --------------------------------------------------
    description_html = make_usernames_clickable(media.description or "")
    
    context = {
        "media": media,
        "related_media": media_batch,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "description": description_html,
        "is_buddy": is_buddy,
        "is_following": is_following,
        "has_blocked_media_owner": has_blocked_media_owner,
        "is_blocked_by_media_owner": is_blocked_by_media_owner,

    }
    return render(request, "explore_detail.html", context)



#___________________________________________________________
#
#
#___________________________________________________________



#____________________________________
#Anonymous & Authenticated Handling
#User Preferences & Personalization
#Media Scoring Logic
#Redis-Based Batch Caching
#Performance Optimizations
#AJAX & Pagination Support
#This function efficiently delivers a personalized, high-performance feed using Redis for caching scores and served media, 
#reducing database load and latency while keeping real-time personalization intact
#____________________________________
#without global cache setup

logger = logging.getLogger(__name__)
PAGE_SIZE = 9
CANDIDATE_POOL_SIZE = 30
GLOBAL_EXPLORE_CAP = 89
CREATOR_COOLDOWN = 7          # posts before same creator can reappear strongly
CATEGORY_STREAK_LIMIT = 3     # avoid too many same-category posts in a row
CREATOR_FATIGUE_WINDOW = 4   # if user saw too many from same creator recently → downrank
TRENDING_FETCH_LIMIT = 20  # Number of trending IDs to pull from Redis
DISCOVERY_FETCH_LIMIT = 50
FOLLOWING_FETCH_LIMIT = 20
MEDIA_OBJECT_CACHE_TIMEOUT = 60 * 5  # 30 minutes
SESSION_SEEN_LIMIT =69  # prevent session from growing forever
CACHE_EXPIRY_DAYS = 1

PERSONALIZED_FETCH_LIMIT = 30  # Limit for personalized recommendations per fetch

# Randomization ranges per tier
RANDOM_TIER_0 = 50   # Personalized
RANDOM_TIER_1 = 100  # Fresh following
RANDOM_TIER_2 = 150  # Preference-matched
RANDOM_TIER_3_4 = 200  # Discovery

# Gaussian noise
GAUSSIAN_STD_DEV = 25  # Standard deviation

# Lucky boost
LUCKY_BOOST_CHANCE = 0.05  # 5% chance
LUCKY_BOOST_VALUES = [50, 100, 150]  # Possible boost amounts

# Configuration constants
FEED_ROTATION_DAYS = 5  # Default rotation period
FEED_ROTATION_DAYS_SMALL_FEED = 3  # For users with <100 available items
FEED_ROTATION_DAYS_LARGE_FEED = 7  # For users with >500 available items

class FeedMediaFetcher:
    """Helper class to organize media fetching logic"""
    
    def __init__(self, user, redis_conn, seen_media_ids, not_interested_media_ids):
        self.user = user
        self.redis_conn = redis_conn
        self.seen_media_ids = seen_media_ids
        self.not_interested_media_ids = not_interested_media_ids
        self.now = timezone.now()
        self.twenty_four_hours_ago = self.now - timedelta(hours=24)
        
        # Fetch user context once
        self._fetch_user_context()
    
    def _fetch_user_context(self):
        """Fetch all user relationships and permissions"""
        self.following_ids = set(Follow.objects.filter(follower=self.user).values_list("following_id", flat=True))
        self.users_blocked_me = set(BlockedUser.objects.filter(blocked=self.user).values_list('blocker', flat=True))
        self.users_i_blocked = set(BlockedUser.objects.filter(blocker=self.user).values_list('blocked', flat=True))
        self.buddy_list = set(Buddy.objects.filter(user=self.user).values_list('buddy', flat=True))
        self.users_who_buddied_me = set(Buddy.objects.filter(buddy=self.user).values_list('user', flat=True))
        self.followed_users = AuthUser.objects.filter(
            follower_set__follower=self.user
        ).exclude(id__in=self.users_blocked_me).exclude(id__in=self.users_i_blocked)
    
    def get_privacy_filter(self):
        """Get privacy filter Q object"""
        return (
            Q(is_private=False) |
            Q(is_private=True, user__in=self.users_who_buddied_me) |
            Q(is_private=True, user=self.user)
        )
    
    def get_base_exclusions(self):
        """Get base exclusions dict"""
        return {
            'id__in': self.seen_media_ids | self.not_interested_media_ids,
            'user__in': self.users_blocked_me | self.users_i_blocked
        }
    
    def fetch_personalized_recommendations(self, pref_obj):
        """Fetch collaborative filtering recommendations"""
        try:
            recommendation_key = f"user:reco:{self.user.id}"
            
            # Fetch more than needed for rotation
            recommended_raw = self.redis_conn.zrevrange(
                recommendation_key, 
                0,
                #30 - 1,  # ← CHANGED FROM 150
                PERSONALIZED_FETCH_LIMIT - 1, 
                withscores=True
            )
            
            # Filter unseen media
            recommended_with_scores = [
                (int(mid), score) 
                for mid, score in recommended_raw 
                if int(mid) not in self.seen_media_ids
            ] [:PERSONALIZED_FETCH_LIMIT]
            
            if not recommended_with_scores:
                return [], {}
            
            recommended_ids = [mid for mid, _ in recommended_with_scores]
            
            # Fetch from database with all filters
            personalized_media = list(
                Media.objects.filter(id__in=recommended_ids)
                .filter(self.get_privacy_filter())
                .exclude(id__in=self.seen_media_ids)  #  CRITICAL
                .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
                .exclude(id__in=self.not_interested_media_ids)
                .select_related('user', 'user__profile')
                .prefetch_related('hashtags', 'likes')
                .annotate(likes_count=Count('likes'))
            )
            '''

            # new ✅ Only fetch what passed Redis filter
            personalized_media = list(
                Media.objects.filter(id__in=recommended_ids)
                .filter(self.get_privacy_filter())
                .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
                .exclude(id__in=self.not_interested_media_ids)
                .select_related('user', 'user__profile')
                .prefetch_related('hashtags')  # ← Reduced: removed 'likes'
                .only('id', 'user_id', 'file', 'thumbnail', 'description', 
                      'category', 'created_at', 'view_count', 'is_private')  # ← Only needed fields
            )
            '''

            # Map scores
            scores_map = {mid: score for mid, score in recommended_with_scores}
            
            logger.info(f"Fetched {len(personalized_media)} personalized recommendations for user {self.user.id}")
            return personalized_media, scores_map
            
        except Exception as e:
            logger.warning(f"Error fetching personalized recommendations: {e}")
            return [], {}
    
    def fetch_fresh_following(self):
        """Fetch fresh content from followed users (<24h)"""
        return list(
            Media.objects.filter(
                Q(user__in=self.followed_users) | Q(user__in=self.buddy_list)
            )
            .filter(created_at__gte=self.twenty_four_hours_ago)
            .filter(self.get_privacy_filter())
            .exclude(id__in=self.seen_media_ids)  #  CRITICAL
            .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
            .exclude(id__in=self.not_interested_media_ids)
            .select_related('user', 'user__profile')
            .prefetch_related('hashtags', 'likes')
            .annotate(likes_count=Count('likes'))
            .order_by('-created_at')[:FOLLOWING_FETCH_LIMIT]
        )
    
    def fetch_older_following(self):
        """Fetch older content from followed users (>24h)"""
        return list(
            Media.objects.filter(
                Q(user__in=self.followed_users) | Q(user__in=self.buddy_list)
            )
            .filter(created_at__lt=self.twenty_four_hours_ago)
            .filter(self.get_privacy_filter())
            .exclude(id__in=self.seen_media_ids)  #  CRITICAL
            .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
            .exclude(id__in=self.not_interested_media_ids)
            .select_related('user', 'user__profile')
            .prefetch_related('hashtags', 'likes')
            .annotate(likes_count=Count('likes'))
            .order_by('-created_at')[:FOLLOWING_FETCH_LIMIT]
        )
    
    def fetch_trending(self):
        """Fetch trending media from Redis"""
        try:
            trending_ids_raw = self.redis_conn.zrevrange(
                TRENDING_ZSET_KEY, 
                0, 
                TRENDING_FETCH_LIMIT - 1
            )
            
            # Filter by seen_media_ids BEFORE database query
            trending_ids = [
                int(mid) 
                for mid in trending_ids_raw 
                if int(mid) not in self.seen_media_ids
            ]
            
            if not trending_ids:
                return []
            
            return list(
                Media.objects.filter(id__in=trending_ids)
                .filter(self.get_privacy_filter())
                .exclude(id__in=self.seen_media_ids)  #  CRITICAL - DOUBLE FILTER FOR SAFETY
                .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
                .exclude(id__in=self.not_interested_media_ids)
                .select_related('user', 'user__profile')
                .prefetch_related('hashtags', 'likes')
                .annotate(likes_count=Count('likes'))
            )
            
        except Exception as e:
            logger.warning(f"Error fetching trending media: {e}")
            return []
    
    def fetch_discovery(self, exclude_ids):
        """Fetch discovery media"""
        return list(
            Media.objects.filter(
                Q(is_private=False, user__profile__is_private=False) |
                Q(is_private=True, user__in=self.users_who_buddied_me) |
                Q(is_private=True, user=self.user)
            )
            .exclude(id__in=exclude_ids | self.seen_media_ids | self.not_interested_media_ids)  #  CRITICAL
            .exclude(user__in=self.users_blocked_me | self.users_i_blocked)
            .select_related('user', 'user__profile')
            .prefetch_related('hashtags', 'likes')
            .annotate(likes_count=Count('likes'))
            .order_by('-created_at')[:DISCOVERY_FETCH_LIMIT]
        )

    '''
    def enforce_creator_diversity(self, sorted_media, max_consecutive=2):
        """
        Ensure no more than max_consecutive posts from same creator
        """
        result = []
        creator_streak = {}
    
        for media in sorted_media:
            creator_id = media.user_id
            current_streak = creator_streak.get(creator_id, 0)
        
            if current_streak < max_consecutive:
                result.append(media)
                creator_streak[creator_id] = current_streak + 1
            else:
                # Skip this media, reset when we add different creator
                for other_creator in creator_streak:
                    if other_creator != creator_id:
                        creator_streak[creator_id] = 0
                        result.append(media)
                        break
    
        return result

    '''

    '''
    def enforce_category_diversity(self, sorted_media, max_same_category=3):
        """
        Prevent too many consecutive media from same category
        """
        result = []
        category_streak = {}
        last_category = None
    
        for media in sorted_media:
            category = str(media.category or 'uncategorized')
        
            if category != last_category:
                result.append(media)
                last_category = category
                category_streak[category] = 1
            elif category_streak.get(category, 0) < max_same_category:
                result.append(media)
                category_streak[category] += 1
            # else: skip to enforce diversity
    
        return result


    def apply_hashtag_diversity_bonus(self, media, base_score):
        """
        Boost media with hashtags NOT recently seen
        """
        media_hashtags = set(h.name.lower() for h in media.hashtags.all())
        viewed_hashtags = set(t.lower() for t in (self.pref_obj.viewed_hashtags or []))
    
        # Bonus for fresh hashtags
        fresh_hashtags = media_hashtags - viewed_hashtags
        diversity_bonus = len(fresh_hashtags) * 5
    
        return base_score + diversity_bonus
    '''

from .tasks import (
    PENALTY_SAME_CREATOR,
    PENALTY_SAME_CATEGORY,
    PENALTY_SIMILAR_MEDIA,
    PENALTY_SAME_HASHTAGS,
)
class FeedScorer:
    """Helper class for scoring and prioritizing media"""
    
    def __init__(self, pref_obj, personalized_scores_map, now, redis_conn=None):
        self.pref_obj = pref_obj
        self.personalized_scores_map = personalized_scores_map
        self.now = now
        self.all_followed_media_ids = set()
        
        # Get Redis connection
        self.redis_conn = redis_conn or get_redis_connection("default")
        
        # Load penalty data from Redis
        self.load_penalties()

        #  NEW: Load profile category and exposure data
        self.load_profile_category_data()

    def load_penalties(self):
        """Load all penalty data from Redis for fast lookups during scoring"""
        try:
            user_id = self.pref_obj.user.id
            
            # Get creator penalties
            creator_penalties = self.redis_conn.zrange(
                f"user:creator_penalty:{user_id}", 0, -1, withscores=True
            )
            self.creator_penalty_map = {
                int(cid.decode()): count for cid, count in creator_penalties
            }
            
            # Get category penalties
            category_penalties = self.redis_conn.zrange(
                f"user:category_penalty:{user_id}", 0, -1, withscores=True
            )
            self.category_penalty_map = {
                cat.decode(): count for cat, count in category_penalties
            }
            
            # Get similar media penalties
            self.similar_ni_media = set(
                int(mid.decode()) for mid in self.redis_conn.zrange(
                    f"user:similar_ni:{user_id}", 0, -1
                )
            )
            
            logger.debug(
                f"Loaded penalties for user {user_id}: "
                f"{len(self.creator_penalty_map)} creators, "
                f"{len(self.category_penalty_map)} categories, "
                f"{len(self.similar_ni_media)} similar media"
            )
        
        except Exception as e:
            logger.warning(f"Failed to load penalties: {e}")
            # Fallback to empty penalty maps
            self.creator_penalty_map = {}
            self.category_penalty_map = {}
            self.similar_ni_media = set()
    
    
    def load_profile_category_data(self):
        """
         NEW: Load profile category and exposure tracking
        """
        try:
            user_id = self.pref_obj.user.id
            
            # Get user's profile category
            try:
                self.profile_category = self.pref_obj.user.profile.category
            except:
                self.profile_category = None
            
            # Get category exposure (how much of each category user has seen recently)
            exposure_key = f"user:category_exposure:{user_id}"
            category_exposures = self.redis_conn.zrange(
                exposure_key, 0, -1, withscores=True
            )
            
            # Count exposures per category
            self.category_exposure_count = {}
            for cat_bytes, timestamp in category_exposures:
                category = cat_bytes.decode()
                self.category_exposure_count[category] = self.category_exposure_count.get(category, 0) + 1
            
            logger.debug(
                f"Profile category: {self.profile_category}, "
                f"Recent exposures: {self.category_exposure_count}"
            )
        
        except Exception as e:
            logger.warning(f"Failed to load profile category data: {e}")
            self.profile_category = None
            self.category_exposure_count = {}
    
    '''
    # ✅ ADD THIS NEW METHOD
    def add_intelligent_noise(self, base_score, priority_tier):
        """
        Add intelligent noise proportional to score magnitude and tier.
        
        Logic:
        - Personalized (tier 0): Small noise (5% of score) - preserve ranking
        - Fresh Following (tier 1): Medium noise (10%) - some variation  
        - Preference-matched (tier 2): Higher noise (15%) - more discovery
        - Older Following (tier 3): High noise (25%) - shuffle diversity
        - Discovery (tier 4): Very high noise (30%) - maximum serendipity
        
        Args:
            base_score: Score before noise
            priority_tier: 0-4 (0=highest priority, 4=lowest)
            
        Returns:
            Score with intelligent noise applied
        """
        import random
        
        # Define noise intensity per tier
        noise_factors = {
            0: 0.05,   # Personalized: 5% noise
            1: 0.10,   # Fresh following: 10% noise
            2: 0.15,   # Preference-matched: 15% noise
            3: 0.25,   # Older following: 25% noise
            4: 0.30,   # Discovery: 30% noise
        }
        
        noise_intensity = noise_factors.get(priority_tier, 0.20)
        
        # Calculate noise magnitude as percentage of base score
        # This ensures high-scoring items stay high, but get shuffled
        noise_magnitude = base_score * noise_intensity
        
        # Apply Gaussian noise (bell curve distribution)
        # Mean = 0, StdDev = noise_magnitude / 2
        # This gives 95% of noise values between -noise_magnitude and +noise_magnitude
        try:
            gaussian_noise = random.gauss(0, noise_magnitude / 2)
        except:
            # Fallback if gauss fails
            gaussian_noise = random.uniform(-noise_magnitude, noise_magnitude)
        
        # Apply noise
        noisy_score = base_score + gaussian_noise
        
        # Optional: Ensure score doesn't go negative
        noisy_score = max(0, noisy_score)
        
        return noisy_score
    '''


    def apply_penalties(self, media, base_score):
        """
        Apply graduated penalties to base score
        
        Args:
            media: Media object
            base_score: Base score before penalties
            
        Returns:
            Penalized score (float)
        """
        penalty_multiplier = 2.0
        penalties_applied = []
        
        # 1. Creator penalty (60% reduction per strike, graduated)
        creator_id = media.user_id
        if creator_id in self.creator_penalty_map:
            penalty_count = self.creator_penalty_map[creator_id]
            # Graduated: 1 strike = 0.4, 2 strikes = 0.16, 3+ strikes = 0.064
            creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count, 3)
            #creator_penalty = PENALTY_SAME_CREATOR ** min(penalty_count / 2, 2)

            penalty_multiplier *= creator_penalty
            penalties_applied.append(f"creator({penalty_count})")
        
        # 2. Category penalty (30% reduction per strike, graduated)
        category = getattr(media, 'category', None)
        if category and str(category) in self.category_penalty_map:
            penalty_count = self.category_penalty_map[str(category)]
            # Graduated: spread over more strikes (divide by 2)
            category_penalty = PENALTY_SAME_CATEGORY ** min(penalty_count / 2, 2)
            penalty_multiplier *= category_penalty
            penalties_applied.append(f"category({penalty_count})")
        
        # 3. Similar media penalty (40% reduction, flat)
        if media.id in self.similar_ni_media:
            penalty_multiplier *= PENALTY_SIMILAR_MEDIA
            penalties_applied.append("similar")
        
        # Apply combined penalty
        penalized_score = base_score * penalty_multiplier
        
        # Log if penalties were applied (for debugging)
        if penalties_applied:
            logger.debug(
                f"Applied penalties to media {media.id}: {', '.join(penalties_applied)} | "
                f"Score: {base_score:.1f} → {penalized_score:.1f} "
                f"({(1-penalty_multiplier)*100:.0f}% reduction)"
            )
        
        return penalized_score
    
    
    def apply_profile_category_boost(self, media, base_score):
        """
         NEW: Apply gentle profile category boost with time decay and saturation prevention
        """
        boost = 0
        boost_reason = []
        
        media_category = getattr(media, 'category', None)
        if not media_category:
            return base_score
        
        media_category_str = str(media_category)
        
        # 1. PROFILE CATEGORY MATCH (Gentle Boost)
        if self.profile_category and media_category_str == self.profile_category:
            category_boost = 25  # Gentle boost
            
            # Time decay: Older content gets less boost
            age_hours = (self.now - media.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))  # Decay over 3 days
            category_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = self.category_exposure_count.get(media_category_str, 0)
            if exposure_count > 5:
                saturation_factor = max(0.2, 1 - (exposure_count - 5) * 0.1)
                category_boost *= saturation_factor
                boost_reason.append(f"saturated({exposure_count})")
            
            boost += category_boost
            boost_reason.append(f"profile_match({category_boost:.1f})")
        
        # 2. LIKED CATEGORIES (From engagement history)
        liked_categories = self.pref_obj.liked_categories or []
        if media_category_str in liked_categories:
            liked_boost = 15  # Smaller boost
            
            # Time decay
            age_hours = (self.now - media.created_at).total_seconds() / 3600
            time_decay_factor = max(0.3, 1 - (age_hours / 72))
            liked_boost *= time_decay_factor
            
            # Saturation prevention
            exposure_count = self.category_exposure_count.get(media_category_str, 0)
            if exposure_count > 8:
                saturation_factor = max(0.3, 1 - (exposure_count - 8) * 0.08)
                liked_boost *= saturation_factor
            
            boost += liked_boost
            boost_reason.append(f"liked_cat({liked_boost:.1f})")
        
        # 3. DIVERSITY BONUS
        exposure_count = self.category_exposure_count.get(media_category_str, 0)
        if exposure_count == 0:
            boost += 10
            boost_reason.append("fresh_category")
        
        boosted_score = base_score + boost
        
        if boost > 0:
            logger.debug(
                f"Profile category boost for media {media.id}: "
                f"{base_score:.1f} → {boosted_score:.1f} ({', '.join(boost_reason)})"
            )
        
        return boosted_score
    

    def set_followed_media_ids(self, fresh_media, older_media):
        """Set the followed media IDs for scoring"""
        self.all_followed_media_ids = {m.id for m in fresh_media} | {m.id for m in older_media}
    

    from collections import deque, defaultdict

    '''
    def enforce_creator_diversity(self, sorted_media, max_consecutive=1):
        diversified = []
        recent_creators = deque(maxlen=max_consecutive)

        remaining = list(sorted_media)

        while remaining:
            placed = False

            for i, media in enumerate(remaining):
                creator_id = media.user_id

                if len(recent_creators) < max_consecutive:
                    diversified.append(media)
                    recent_creators.append(creator_id)
                    remaining.pop(i)
                    placed = True
                    break

                # Check if last N posts are all from same creator
                if not all(c == creator_id for c in recent_creators):
                    diversified.append(media)
                    recent_creators.append(creator_id)
                    remaining.pop(i)
                    placed = True
                    break

            if not placed:
                diversified.extend(remaining)
                break

        return diversified
    '''

    def enforce_creator_diversity(
        self,
        sorted_media,
        max_consecutive=1,
        max_posts_per_creator=2
    ):
        diversified = []
        recent_creators = deque(maxlen=max_consecutive)

        # Total posts shown per creator in this feed
        creator_counts = defaultdict(int)

        remaining = list(sorted_media)

        while remaining:
            placed = False

            for i, media in enumerate(remaining):
                creator_id = media.user_id

                # Hard cap: max 2 posts from creator
                if creator_counts[creator_id] >= max_posts_per_creator:
                    continue

                # First few posts
                if len(recent_creators) < max_consecutive:
                    diversified.append(media)
                    recent_creators.append(creator_id)
                    creator_counts[creator_id] += 1
                    remaining.pop(i)
                    placed = True
                    break

                # Prevent consecutive creator repetition
                if not all(c == creator_id for c in recent_creators):
                    diversified.append(media)
                    recent_creators.append(creator_id)
                    creator_counts[creator_id] += 1
                    remaining.pop(i)
                    placed = True
                    break

            if not placed:
                break

        return diversified


    def calculate_priority_and_score(self, media, source, is_fresh_followed=False, is_personalized=False):
        """
        Calculate priority tier and score for media with ENHANCED RANDOMIZATION
        
        Returns: (priority_tier, score, media)
        Tiers:
          0 = Personalized (collaborative filtering) - Less random
          1 = Fresh following (<24h) - Medium random
          2 = Preference-matched (trending/discovery) - More random
          3 = Older following (>24h) - Most random
          4 = General discovery - Most random
        """
        import random  # Make sure random is imported
        
        # Calculate base score
        try:
            base_score = calculate_media_score(
                media,
                liked_hashtags=self.pref_obj.liked_hashtags or [],
                not_interested_hashtags=self.pref_obj.not_interested_hashtags or [],
                viewed_hashtags=self.pref_obj.viewed_hashtags or [],
                search_hashtags=self.pref_obj.search_hashtags or [],
                user_category_preferences=self.pref_obj.liked_categories or [],
                followed_users_media_ids=self.all_followed_media_ids,
                followed_users_descriptions_matches=False,
                user=self.pref_obj.user
            )
        except Exception as e:
            logger.warning(f"Error calculating media score for {media.id}: {e}")
            # Fallback scoring
            base_score = (getattr(media, 'likes_count', 0) or 0) + (media.view_count or 0) * 0.01
        
        priority = 4  # Default: general discovery
        
        # ============================================================
        # TIER ASSIGNMENT & BASE SCORE BOOSTS
        # ============================================================
        
        # Tier 0: Personalized recommendations (from collaborative filtering)
        if is_personalized:
            priority = 0
            redis_score = self.personalized_scores_map.get(media.id, 0)
            base_score += redis_score * 5 + 50  # Massive boost for personalized
        
        # Tier 1: Fresh media from followed users (<24 hours old)
        elif is_fresh_followed:
            priority = 1
            # Add recency bonus
            age_hours = (self.now - media.created_at).total_seconds() / 3600
            if age_hours < 6:  # Less than 6 hours
                base_score += 70
            elif age_hours < 12:  # Less than 12 hours
                base_score += 35
            elif age_hours < 24:  # Less than 24 hours
                base_score += 19
        
        # Tier 3: Older media from followed users (>24 hours old)
        elif source == 'older_followed':
            priority = 3
            base_score += 5  # Small boost for being from followed users
        
        # Tier 2: Preference-matched content (trending/discovery with user interests)
        elif source in ['trending', 'discovery']:
            try:
                media_hashtags = [h.name for h in media.hashtags.all()]
                media_category = getattr(media, 'category', None)
                
                # Check for preference matches
                has_liked_hashtag = any(h in (self.pref_obj.liked_hashtags or []) for h in media_hashtags)
                has_search_hashtag = any(h in (self.pref_obj.search_hashtags or []) for h in media_hashtags)
                has_liked_category = media_category in (self.pref_obj.liked_categories or [])
                
                if has_liked_hashtag or has_search_hashtag or has_liked_category:
                    priority = 2
                    base_score += 51  # Boost for matching preferences
            except Exception as e:
                logger.warning(f"Error checking preferences for {media.id}: {e}")
        
        # ============================================================
        # STEP 3: APPLY PENALTIES (NEW!)
        # ============================================================

        #  APPLY PROFILE CATEGORY BOOST (NEW!)
        base_score = self.apply_profile_category_boost(media, base_score)

        base_score = self.apply_penalties(media, base_score)

        # ============================================================
        # STEP 4: ENHANCED SMART RANDOMIZATION
        # ============================================================
        
        # Tier-specific randomization (different ranges per priority)
        if priority == 0:  # Personalized - keep mostly stable, but shuffle
            random_factor = random.uniform(0, 50)
            
        elif priority == 1:  # Fresh following - medium shuffle
            random_factor = random.uniform(0, 100)
            
        elif priority == 2:  # Preference-matched - more shuffle
            random_factor = random.uniform(0, 150)
            
        else:  # Tiers 3 & 4 - maximum shuffle for discovery
            random_factor = random.uniform(0, 200)
        
        # Add gaussian noise for natural distribution
        # Creates bell curve: most values cluster near 0, some outliers
        try:
            gaussian_noise = random.gauss(0, 25)  # Mean=0, StdDev=25
        except:
            # Fallback if gauss fails (rare)
            gaussian_noise = random.uniform(-25, 25)
        
        # Optional: Lucky boost (5% chance for big jump)
        # This creates occasional surprises in the feed
        lucky_boost = 0
        if random.random() < 0.05:  # 5% chance
            lucky_boost = random.choice([50, 100, 150])
        
        # Calculate final score
        final_score = base_score + random_factor + gaussian_noise + lucky_boost
        
        '''
        # ✅ NEW: Use intelligent noise instead of fixed ranges
        final_score = self.add_intelligent_noise(base_score, priority)
    
        # Optional: Keep lucky boost for serendipity (rare surprise)
        if random.random() < 0.05:  # 5% chance
            lucky_boost = random.choice([50, 100, 150])  # Smaller boosts now
            final_score += lucky_boost
            logger.debug(f"Lucky boost applied to media {media.id}: +{lucky_boost}")
        '''

        return (priority, final_score, media)


    
    def score_and_sort_media(self, personalized, fresh_following, older_following, 
                            trending, discovery):
        """Score all media and return sorted list"""
        scored_media = []
        
        # Score each tier
        for m in personalized:
            scored_media.append(
                self.calculate_priority_and_score(m, 'personalized', is_personalized=True)
            )
        
        for m in fresh_following:
            scored_media.append(
                self.calculate_priority_and_score(m, 'fresh_followed', is_fresh_followed=True)
            )
        
        for m in trending:
            scored_media.append(
                self.calculate_priority_and_score(m, 'trending')
            )
        
        for m in older_following:
            scored_media.append(
                self.calculate_priority_and_score(m, 'older_followed')
            )
        
        for m in discovery:
            scored_media.append(
                self.calculate_priority_and_score(m, 'discovery')
            )
        
        # Remove duplicates (keep highest priority version)
        unique_scored = {}
        for priority, score, media in scored_media:
            if media.id not in unique_scored:
                unique_scored[media.id] = (priority, score, media)
            else:
                # Keep the version with higher priority (lower number = higher priority)
                existing_priority, existing_score, _ = unique_scored[media.id]
                if priority < existing_priority or (priority == existing_priority and score > existing_score):
                    unique_scored[media.id] = (priority, score, media)
        
        # Sort by priority tier first, then by score within tier
        sorted_feed = sorted(
            unique_scored.values(),
            key=lambda x: (x[0], -x[1])  # Sort by priority ASC, then score DESC
        )
        #original
        #return [media for _, _, media in sorted_feed], scored_media


        #new implementation for creator diversity
        final_feed = [media for _, _, media in sorted_feed]

        # ------------------------------------
        # Creator diversity
        # ------------------------------------
        final_feed = self.enforce_creator_diversity(
            final_feed,
            max_consecutive=1,
            max_posts_per_creator=2
        )

        return final_feed, scored_media



# ----------------------------------------------------------------------------------
#  ENHANCED: this part GET BOTH CACHE LAYERS entire caching included in this section 
# ----------------------------------------------------------------------------------

def cache_feed_rotation(redis_conn, user_id, media_ids, rotation_days=None):
    """
    Cache media IDs for feed rotation (temporary exclusion)
    
    This prevents the same content from appearing too frequently in the feed.
    Media is cached with an expiry timestamp and will be excluded from the feed
    until the rotation period expires.
    
    Args:
        redis_conn: Redis connection
        user_id: User ID
        media_ids: List of media IDs to cache for rotation
        rotation_days: How long to exclude (default from settings)
    
    Returns:
        bool: Success status
    """
    try:
        if not media_ids:
            return True
        
        # Use default if not specified
        if rotation_days is None:
            rotation_days = FEED_ROTATION_DAYS
        
        cache_key = f"user:feed_rotation:{user_id}"
        now = int(time.time())
        expiry_timestamp = now + (rotation_days * 24 * 60 * 60)
        
        # Add media with expiry timestamp as score
        # ZSET allows efficient time-based queries
        mapping = {mid: expiry_timestamp for mid in media_ids}
        redis_conn.zadd(cache_key, mapping)
        
        # Cleanup: Remove expired items (score < now)
        removed_count = redis_conn.zremrangebyscore(cache_key, 0, now)
        
        # Set overall key expiry (30 days for auto-cleanup)
        redis_conn.expire(cache_key, 60 * 60 * 24 * 30)
        
        logger.debug(
            f"Cached {len(media_ids)} media for rotation (user {user_id}, "
            f"{rotation_days}d period). Cleaned {removed_count} expired items."
        )
        
        return True
    
    except Exception as e:
        logger.warning(f"Error caching feed rotation for user {user_id}: {e}")
        return False
 
 
def get_rotation_excluded_media(redis_conn, user_id):
    """
    Get media IDs currently in rotation exclusion period
    
    Returns all media that are still within their rotation period and
    should be excluded from the feed. Automatically cleans up expired items.
    
    Args:
        redis_conn: Redis connection
        user_id: User ID
    
    Returns:
        set: Set of media IDs to exclude from feed
    """
    try:
        cache_key = f"user:feed_rotation:{user_id}"
        now = int(time.time())
        
        # Get all media with expiry timestamp > now (still in rotation period)
        excluded_ids = redis_conn.zrangebyscore(
            cache_key,
            now,  # min score (current time)
            '+inf'  # max score (future timestamps)
        )
        
        # Cleanup: Remove expired items (score < now)
        removed_count = redis_conn.zremrangebyscore(cache_key, 0, now)
        
        excluded_set = {int(mid) for mid in excluded_ids}
        
        logger.debug(
            f"Retrieved {len(excluded_set)} rotation-excluded media for user {user_id}. "
            f"Cleaned {removed_count} expired items."
        )
        
        return excluded_set
    
    except Exception as e:
        logger.warning(f"Error fetching rotation excluded media for user {user_id}: {e}")
        return set()
 
 
def get_optimal_rotation_period(available_media_count):
    """
    Calculate optimal rotation period based on available content
    
    Adjusts rotation period to prevent feed exhaustion for users
    with small following lists while maximizing variety for users
    with large following lists.
    
    Args:
        available_media_count: Number of available media items for user
    
    Returns:
        int: Rotation period in days
    """
    if available_media_count < 100:
        # Small feed: Use shorter rotation to prevent exhaustion
        return FEED_ROTATION_DAYS_SMALL_FEED
    elif available_media_count > 500:
        # Large feed: Use longer rotation for more variety
        return FEED_ROTATION_DAYS_LARGE_FEED
    else:
        # Medium feed: Use default
        return FEED_ROTATION_DAYS
 
 
def reset_feed_rotation_cache(redis_conn, user_id):
    """
    Reset feed rotation cache for a user
    
    Deletes all rotation-cached media, allowing the full feed to be
    available again. Useful for testing or when combined with engagement
    cache reset.
    
    Args:
        redis_conn: Redis connection
        user_id: User ID
    
    Returns:
        bool: Success status
    """
    try:
        cache_key = f"user:feed_rotation:{user_id}"
        deleted = redis_conn.delete(cache_key)
        
        logger.info(f"Reset rotation cache for user {user_id}: {deleted} key deleted")
        
        return True
    
    except Exception as e:
        logger.warning(f"Error resetting rotation cache for user {user_id}: {e}")
        return False

# ----------------------------------------------------------------------------------
#  ENHANCED: this part GET BOTH CACHE LAYERS entire caching included in this section
# ----------------------------------------------------------------------------------


def get_cached_seen_media(redis_conn, user_id):
    """Get seen media from Redis cache"""
    try:
        cache_key = f"user:seen_feed:{user_id}"
        seen_ids = redis_conn.smembers(cache_key)
        return {int(sid) for sid in seen_ids}
    except Exception as e:
        logger.warning(f"Error fetching cached seen media: {e}")
        return set()


def cache_seen_media(redis_conn, user_id, media_ids):
    """Cache seen media IDs in Redis"""
    try:
        cache_key = f"user:seen_feed:{user_id}"
        
        # Add new IDs to set
        if media_ids:
            redis_conn.sadd(cache_key, *media_ids)
        
        # Set expiry (30 days)
        redis_conn.expire(cache_key, 60 * 60 * 24 * CACHE_EXPIRY_DAYS)
        
        return True
    except Exception as e:
        logger.warning(f"Error caching seen media: {e}")
        return False


def reset_cached_seen_media(redis_conn, user_id):
    """Reset cached seen media"""
    try:
        cache_key = f"user:seen_feed:{user_id}"
        deleted = redis_conn.delete(cache_key)
        logger.info(f"Reset seen media cache for user {user_id}: {deleted} keys deleted")
        return True
    except Exception as e:
        logger.warning(f"Error resetting cached seen media: {e}")
        return False


# =====================================================================
# HELPER FUNCTION - APPLY PROFILE CATEGORY BOOST (NEW!)
# =====================================================================
def track_category_exposure(redis_conn, user_id, page_obj):
    """
    Track which categories user has seen recently to prevent saturation
    
    Redis key: user:category_exposure:{user_id}
    Format: ZSET with category -> timestamp
    """
    try:
        now = int(time.time())
        exposure_key = f"user:category_exposure:{user_id}"
        
        # Track each category seen in this page
        for media in page_obj:
            category = getattr(media, 'category', None)
            if category:
                # Add with current timestamp
                redis_conn.zadd(exposure_key, {category: now})
        
        # Remove old exposures (older than 1 hour)
        one_hour_ago = now - 3600
        redis_conn.zremrangebyscore(exposure_key, 0, one_hour_ago)
        
        # Set expiry
        redis_conn.expire(exposure_key, 60 * 60 * 2)  # 2 hours
        
    except Exception as e:
        logger.warning(f"Category exposure tracking failed: {e}")



def following_media(request):
    """
    Main feed view with persistent caching and privacy enforcement
    
    Features:
    - Redis-based persistent seen media tracking
    - Feed rotation cache (3-5 day temporary exclusion)
    - Five-tier priority system
    - Collaborative filtering integration
    -  Privacy-aware filtering:
      - User profile private → visible only to followers
      - Media private → visible only to buddy list
    - Anti-repetition guaranteed
    """
    user = request.user
    
    # --------------------------------------------------
    # ANONYMOUS USERS
    # --------------------------------------------------
    if not user.is_authenticated:
        return handle_anonymous_user(request)
    
    # --------------------------------------------------
    # REDIS CONNECTION & ACTIVE USER TRACKING
    # --------------------------------------------------
    redis_conn = get_redis_connection("default")
    
    try:
        now_ts = int(time.time())
        cutoff = now_ts - 3600
        redis_conn.zadd("active:users", {user.id: now_ts})
        redis_conn.zremrangebyscore("active:users", 0, cutoff)
    except Exception as e:
        logger.warning(f"Active user tracking failed: {e}")
    
    # --------------------------------------------------
    # GET BOTH CACHE LAYERS
    # --------------------------------------------------
    # Layer 1: Engagement-based cache (permanent)
    engagement_seen_ids = get_cached_seen_media(redis_conn, user.id)
    
    # Layer 2: Rotation cache (temporary, 3-5 days)
    rotation_excluded_ids = get_rotation_excluded_media(redis_conn, user.id)
    
    # Combine both exclusions
    cached_seen_media_ids = engagement_seen_ids | rotation_excluded_ids
    
    logger.info(
        f"User {user.id} - Engagement: {len(engagement_seen_ids)}, "
        f"Rotation: {len(rotation_excluded_ids)}, "
        f"Total excluded: {len(cached_seen_media_ids)}"
    )
    
    # --------------------------------------------------
    # USER PREFERENCES
    # --------------------------------------------------
    pref_obj, _ = UserHashtagPreference.objects.get_or_create(user=user)
    not_interested_media_ids = set(pref_obj.not_interested_media) if pref_obj.not_interested_media else set()
    

    # --------------------------------------------------
    # LOAD HEAVILY PENALIZED CREATORS (7+ penalties = complete filter)
    # --------------------------------------------------
    try:
        creator_penalties = redis_conn.zrange(
            f"user:creator_penalty:{user.id}", 0, -1, withscores=True
        )
        heavily_penalized_creators = {
            int(cid.decode()) for cid, count in creator_penalties if count >= 7
        }
        logger.info(f"User {user.id}: {len(heavily_penalized_creators)} heavily penalized creators will be filtered")
    except Exception as e:
        logger.warning(f"Failed to load creator penalties: {e}")
        heavily_penalized_creators = set()


    # --------------------------------------------------
    # FETCH ALL MEDIA POOLS
    # --------------------------------------------------
    fetcher = FeedMediaFetcher(user, redis_conn, cached_seen_media_ids, not_interested_media_ids)
    
    personalized_media, personalized_scores = fetcher.fetch_personalized_recommendations(pref_obj)
    fresh_following = fetcher.fetch_fresh_following()
    older_following = fetcher.fetch_older_following()
    trending_media = fetcher.fetch_trending()
    
    # Discovery (exclude already fetched)
    exclude_ids = (
        {m.id for m in personalized_media} |
        {m.id for m in fresh_following} |
        {m.id for m in older_following} |
        {m.id for m in trending_media}
    )
    discovery_media = fetcher.fetch_discovery(exclude_ids)
    

    # --------------------------------------------------
    #  NEW: PRIVACY FILTERING
    # --------------------------------------------------
    #from service_auth.notion.models import Follow
    #from .models import Buddy
    
    # Get following list (for private profile access)
    following_ids = set(
        Follow.objects.filter(
            follower=user
        ).values_list('following_id', flat=True)
    )
    
    # Get users who have us in their buddy list (for private media access)
    users_who_buddied_me = set(
        Buddy.objects.filter(
            buddy=user
        ).values_list('user_id', flat=True)
    )
    
    logger.info(
        f"User {user.id} privacy context: "
        f"Following {len(following_ids)} users, "
        f"Buddied by {len(users_who_buddied_me)} users"
    )
    
    def filter_by_privacy(media_list):
        """
        Filter media list based on privacy rules
        
        Rules:
        1. Profile private → Only followers can see
        2. Media private → Only buddy list can see
        """
        filtered = []
        for media in media_list:
            # Rule 1: Profile privacy check
            profile_allowed = (
                not media.user.profile.is_private or  # Public profile
                media.user_id in following_ids  # Or we follow them
            )
            
            # Rule 2: Media privacy check
            media_allowed = (
                not media.is_private or  # Public media
                media.user_id in users_who_buddied_me  # Or owner buddied us
            )
            
            # Must pass BOTH checks
            if profile_allowed and media_allowed:
                filtered.append(media)
        
        return filtered
    
    # Apply privacy filter to all pools
    personalized_media = filter_by_privacy(personalized_media)
    fresh_following = filter_by_privacy(fresh_following)
    older_following = filter_by_privacy(older_following)
    trending_media = filter_by_privacy(trending_media)
    discovery_media = filter_by_privacy(discovery_media)
    
    logger.info(
        f"User {user.id} after privacy filtering - "
        f"Personalized: {len(personalized_media)}, "
        f"Fresh: {len(fresh_following)}, "
        f"Older: {len(older_following)}, "
        f"Trending: {len(trending_media)}, "
        f"Discovery: {len(discovery_media)}"
    )
    # --------------------------------------------------
    #  END PRIVACY FILTERING
    # --------------------------------------------------


    # --------------------------------------------------
    # FILTER HEAVILY PENALIZED CREATORS (7+ penalties)
    # --------------------------------------------------
    if heavily_penalized_creators:
        before_counts = {
            'personalized': len(personalized_media),
            'fresh': len(fresh_following),
            'older': len(older_following),
            'trending': len(trending_media),
            'discovery': len(discovery_media)
        }
    
        # Filter each pool
        personalized_media = [m for m in personalized_media if m.user_id not in heavily_penalized_creators]
        fresh_following = [m for m in fresh_following if m.user_id not in heavily_penalized_creators]
        older_following = [m for m in older_following if m.user_id not in heavily_penalized_creators]
        trending_media = [m for m in trending_media if m.user_id not in heavily_penalized_creators]
        discovery_media = [m for m in discovery_media if m.user_id not in heavily_penalized_creators]
    
        after_counts = {
            'personalized': len(personalized_media),
            'fresh': len(fresh_following),
            'older': len(older_following),
            'trending': len(trending_media),
            'discovery': len(discovery_media)
        }
    
        logger.info(f"Filtered heavily penalized creators: Before={before_counts}, After={after_counts}")


    # --------------------------------------------------
    # CHECK IF CACHE SHOULD BE RESET
    # --------------------------------------------------
    total_available = (
        len(personalized_media) + len(fresh_following) +
        len(older_following) + len(trending_media) + len(discovery_media)
    )
    
    if total_available < PAGE_SIZE and len(cached_seen_media_ids) > 0:
        logger.info(f"Exhausted all media for user {user.id}. Resetting caches. "
                   f"Seen: {len(cached_seen_media_ids)}, Available: {total_available}")
        
        # Reset BOTH caches and re-fetch
        reset_cached_seen_media(redis_conn, user.id)
        reset_feed_rotation_cache(redis_conn, user.id)  #  NEW
        cached_seen_media_ids = set()
        
        # Re-create fetcher with empty cache
        fetcher = FeedMediaFetcher(user, redis_conn, cached_seen_media_ids, not_interested_media_ids)
        
        personalized_media, personalized_scores = fetcher.fetch_personalized_recommendations(pref_obj)
        fresh_following = fetcher.fetch_fresh_following()
        older_following = fetcher.fetch_older_following()
        trending_media = fetcher.fetch_trending()
        
        exclude_ids = (
            {m.id for m in personalized_media} | {m.id for m in fresh_following} |
            {m.id for m in older_following} | {m.id for m in trending_media}
        )
        discovery_media = fetcher.fetch_discovery(exclude_ids)

        
        #  RE-APPLY PRIVACY FILTERING after cache reset
        personalized_media = filter_by_privacy(personalized_media)
        fresh_following = filter_by_privacy(fresh_following)
        older_following = filter_by_privacy(older_following)
        trending_media = filter_by_privacy(trending_media)
        discovery_media = filter_by_privacy(discovery_media)
        
        # RE-APPLY PENALTY FILTERING after cache reset
        if heavily_penalized_creators:
            personalized_media = [m for m in personalized_media if m.user_id not in heavily_penalized_creators]
            fresh_following = [m for m in fresh_following if m.user_id not in heavily_penalized_creators]
            older_following = [m for m in older_following if m.user_id not in heavily_penalized_creators]
            trending_media = [m for m in trending_media if m.user_id not in heavily_penalized_creators]
            discovery_media = [m for m in discovery_media if m.user_id not in heavily_penalized_creators]


        total_available = (
            len(personalized_media) + len(fresh_following) +
            len(older_following) + len(trending_media) + len(discovery_media)
        )
        logger.info(f"After reset - Available: {total_available}")
    
    # --------------------------------------------------
    # SCORE AND SORT MEDIA
    # --------------------------------------------------
    scorer = FeedScorer(pref_obj, personalized_scores, timezone.now(), redis_conn)
    scorer.set_followed_media_ids(fresh_following, older_following)
    
    final_feed, scored_media = scorer.score_and_sort_media(
        personalized_media, fresh_following, older_following,
        trending_media, discovery_media
    )

    #final_feed = scorer.enforce_creator_diversity(final_feed, max_consecutive=2)

    
    # Apply description formatting
    for media in final_feed:
        media.description = make_usernames_clickable(media.description)
    
    # --------------------------------------------------
    # PAGINATION
    # --------------------------------------------------
    paginator = Paginator(final_feed, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # --------------------------------------------------
    # BUILD RESPONSE & TRACK VIEWS
    # --------------------------------------------------
    media_list = []
    newly_seen_ids = []
    
    for m in page_obj:
        # Build media dict
        media_dict = build_media_response_dict(m, user, fetcher.following_ids)
        media_list.append(media_dict)
        newly_seen_ids.append(m.id)
    
    # --------------------------------------------------
    # TRACK CATEGORY EXPOSURE & ROTATION CACHE
    # --------------------------------------------------
    # Don't auto-cache engagement - wait for media_engagement view
    # But DO cache for rotation (prevent repetition)
    if page_obj and user.id:
        # Track category exposure
        track_category_exposure(redis_conn, user.id, page_obj)
        
        #  NEW: Cache displayed media for rotation
        displayed_media_ids = [m.id for m in page_obj]
        if displayed_media_ids:
            rotation_days = get_optimal_rotation_period(total_available)
            cache_feed_rotation(redis_conn, user.id, displayed_media_ids, rotation_days)
            logger.info(
                f"User {user.id}: Tracked {len(page_obj)} category exposures, "
                f"cached {len(displayed_media_ids)} for rotation ({rotation_days}d)"
            )
    
    # --------------------------------------------------
    # LOG FEED COMPOSITION
    # --------------------------------------------------
    tier_counts = {i: len([m for p, s, m in scored_media if p == i]) for i in range(5)}
    logger.info(
        f"Feed for user {user.id}: "
        f"Tier0(Personalized): {tier_counts[0]}, "
        f"Tier1(Fresh): {tier_counts[1]}, "
        f"Tier2(Matched): {tier_counts[2]}, "
        f"Tier3(Older): {tier_counts[3]}, "
        f"Tier4(Discovery): {tier_counts[4]}"
    )
    
    # --------------------------------------------------
    # RETURN RESPONSE
    # --------------------------------------------------
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'media': media_list,
            'has_next': page_obj.has_next()
        })
    
    return render(request, 'following_media.html', {
        'page_obj': page_obj,
        'following_ids': fetcher.following_ids
    })


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def handle_anonymous_user(request):
    """Handle anonymous user feed"""
    seen_media_ids = set(request.session.get('seen_media_ids', []))
    
    explore_media_qs = Media.objects.filter(
        is_private=False,
        user__profile__is_private=False
    ).exclude(id__in=seen_media_ids)\
     .select_related('user', 'user__profile')\
     .prefetch_related('hashtags', 'likes')\
     .annotate(likes_count=Count('likes'))\
     .order_by('-created_at')
    
    paginator = Paginator(explore_media_qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    media_list = []
    newly_seen_ids = []
    
    for m in page_obj:
        media_dict = build_anonymous_media_dict(m)
        media_list.append(media_dict)
        newly_seen_ids.append(m.id)
        
        # Increment view count for anonymous
        # TESTING: Commented out to prevent view inflation in feed
        #Media.objects.filter(pk=m.pk).update(view_count=F('view_count') + 1)
    
    # Update session
    if newly_seen_ids:
        updated_seen = list(seen_media_ids) + newly_seen_ids
        request.session['seen_media_ids'] = updated_seen[-SESSION_SEEN_LIMIT:]
        request.session.modified = True
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})
    
    return render(request, 'following_media.html', {
        'page_obj': page_obj,
        'following_ids': set()
    })


def build_media_response_dict(media, user, following_ids):
    """Build media response dictionary"""
    try:
        profile_picture_url = media.user.profile.profile_picture.url
    except:
        profile_picture_url = '/static/images/logo.png'
    
    show_follow = user != media.user and media.user.id not in following_ids
    
    try:
        profile_url = reverse('user_profile:profile', kwargs={'user_id': media.user.id})
    except:
        profile_url = None
    
    return {
        'id': media.id,
        'file_url': media.file.url,
        'is_video': (media.media_type == 'video') or (media.file.name.lower().endswith('.mp4')),
        'user_username': media.user.username,
        'description': media.description,
        'likes_count': getattr(media, 'likes_count', media.likes.count()),
        'is_liked': user in media.likes.all(),
        'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': media.id}),
        'view_count': media.view_count,
        'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': media.id}),
        'profile_url': profile_url,
        'profile_picture_url': profile_picture_url,
        'show_follow': show_follow,
        'follow_url': reverse("user_profile:follow_user", kwargs={"user_id": media.user.id}) if show_follow else None,
        'like_url': reverse('user_profile:like_media', kwargs={'media_id': media.id}),
    }


def build_anonymous_media_dict(media):
    """Build media dict for anonymous users"""
    try:
        profile_picture_url = media.user.profile.profile_picture.url
    except:
        profile_picture_url = '/static/images/logo.png'
    
    try:
        profile_url = reverse('user_profile:profile', kwargs={'user_id': media.user.id})
    except:
        profile_url = None
    
    return {
        'id': media.id,
        'file_url': media.file.url,
        'is_video': (media.media_type == 'video') or (media.file.name.lower().endswith('.mp4')),
        'user_username': media.user.username,
        'description': make_usernames_clickable(media.description),
        'likes_count': media.likes.count(),
        'is_liked': False,
        'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': media.id}),
        'view_count': media.view_count,
        'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': media.id}),
        'profile_url': profile_url,
        'like_url': reverse('user_profile:like_media', kwargs={'media_id': media.id}),
        'profile_picture_url': profile_picture_url,
    }


def track_unique_view(media, user):
    """Track unique view for authenticated user"""
    # TESTING: Disabled view tracking in feed
    pass

    '''
    has_viewed = Engagement.objects.filter(
        user=user,
        media=media,
        engagement_type='view'
    ).exists()
    
    if not has_viewed:
        Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
        Engagement.objects.create(
            media=media,
            user=user,
            engagement_type='view'
        )
    '''



#____________________________________
#Anonymous & Authenticated Handling
#User Preferences & Personalization
#Media Scoring Logic
#Redis-Based Batch Caching
#Performance Optimizations
#AJAX & Pagination Support
#This function efficiently delivers a personalized, high-performance feed using Redis for caching scores and served media, 
#reducing database load and latency while keeping real-time personalization intact
#____________________________________

#______________________________
#new function to support jason response of the following_media 
#by loading the following_media.html page initially
#_____________________________

#@login_required
def feed_page(request):
    return render(request, "following_media.html")

#______________________________
#new function to support jason response of the following_media 
#by loading the following_media.html page initially 
#_____________________________


#__________________________________________________________________
#
#
#__________________________________________________________________


@login_required
@require_POST
def media_engagement(request, media_id):
    try:
        media = get_object_or_404(Media, id=media_id)

        data = json.loads(request.body)
        engagement_type = data.get("engagement_type")

        if engagement_type != "view":
            return JsonResponse({"error": "Only 'view' supported"}, status=400)

        created = False

        # --------------------------------
        # SAVE UNIQUE VIEW
        # --------------------------------
        try:
            Engagement.objects.create(
                user=request.user,
                media=media,
                engagement_type="view"
            )
            created = True

        except IntegrityError:
            # View already exists — do nothing
            created = False

        # --------------------------------
        # INCREMENT VIEW COUNT (ONLY IF UNIQUE)
        # --------------------------------
        if created:
            media.view_count = F('view_count') + 1
            media.save(update_fields=["view_count"])

        # --------------------------------
        # REDIS TRACKING (UNCHANGED)
        # --------------------------------
        try:
            redis = get_redis_connection("default")

            user_id = request.user.id
            now = int(time.time())
            cutoff = now - WINDOW_SECONDS

            redis.zadd(f"user:viewed:{user_id}", {media_id: now})
            redis.zremrangebyscore(f"user:viewed:{user_id}", 0, cutoff)
            redis.expire(f"user:viewed:{user_id}", 60 * 60 * 24 * 30)  # ←


            redis.zadd(f"media:viewed_by:{media_id}", {user_id: now})
            redis.zremrangebyscore(f"media:viewed_by:{media_id}", 0, cutoff)
            redis.expire(f"media:viewed_by:{media_id}", 60 * 60 * 24 * 30)  # ←


            redis.zadd("active:users", {user_id: now})
            redis.zremrangebyscore("active:users", 0, cutoff)
            redis.expire("active:users", 60 * 60 * 24 * 7)  # ←

            #  ADD THESE 2 LINES for delayed media viewd id:
            cache_seen_media(redis, user_id, [media_id])
            logger.info(f"Cached media {media_id} as seen for user {user_id} (engagement-based)")
 
        except Exception as e:
            logger.warning(
                f"Redis tracking failed for user {request.user.id}, media {media_id}: {e}"
            )

        return JsonResponse({
            "success": True,
            "unique_view": created
        })

    except Exception as e:
        logger.error(f"Media engagement error: {e}")
        return JsonResponse({"error": "Server error"}, status=500)



@require_POST
def log_interaction(request):
    try:
        if request.content_type != 'application/json':
            return JsonResponse({'error': 'Invalid content type'}, status=400)

        data = json.loads(request.body)
        media_id = data.get('media_id')
        interaction_type = data.get('interaction_type', 'view')

        if not media_id:
            return JsonResponse({'error': 'Missing media_id'}, status=400)

        try:
            media = Media.objects.get(id=media_id)
        except Media.DoesNotExist:
            return JsonResponse({'error': 'Invalid media_id'}, status=400)

        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        if interaction_type not in ['view', 'like', 'comment']:
            return JsonResponse({'error': 'Invalid interaction type'}, status=400)

        # --------------------------------
        # DATABASE STORAGE (unchanged)
        # --------------------------------
        Interaction.objects.create(
            media=media,
            user=request.user,
            interaction_type=interaction_type
        )

        Engagement.objects.create(
            media=media,
            user=request.user,
            engagement_type=interaction_type
        )

        # --------------------------------
        # REDIS BEHAVIOR TRACKING (views only)
        # --------------------------------
        if interaction_type == "view":

            redis = get_redis_connection("default")

            user_id = request.user.id
            now = int(time.time())
            cutoff = now - WINDOW_SECONDS

            print("LOG INTERACTION HIT", user_id, media_id)

            user_viewed_key = f"user:viewed:{user_id}"
            media_viewed_by_key = f"media:viewed_by:{media_id}"

            # User → Media
            redis.zadd(user_viewed_key, {media_id: now})
            redis.zremrangebyscore(user_viewed_key, 0, cutoff)

            # Media → User
            redis.zadd(media_viewed_by_key, {user_id: now})
            redis.zremrangebyscore(media_viewed_by_key, 0, cutoff)

            # Track active users
            redis.zadd("active:users", {user_id: now})
            redis.zremrangebyscore("active:users", 0, cutoff)

        return JsonResponse({'success': True})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    except Exception as e:
        print(f"Error in log_interaction: {e}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

#_________________________________________________________________
#
#
#_________________________________________________________________


# ===============================================================
# ENHANCED USER SEARCH WITH COLLABORATIVE FILTERING
# ===============================================================

@login_required
def search_users(request, user_id):
    """
    Enhanced user search with collaborative filtering integration
    
    Features:
    - Tracks search queries in Redis for recommendations
    - Boosts users based on interaction history
    - Privacy-aware filtering
    - No caching (search results should be fresh)
    """
    query = request.GET.get('q', '').strip()
    profile_user = get_object_or_404(AuthUser, id=user_id)
    redis_conn = get_redis_connection("default")
    
    # Initialize empty queryset
    users = AuthUser.objects.none()
    
    # Privacy checks
    is_blocked = BlockedUser.objects.filter(
        blocker=request.user, 
        blocked=profile_user
    ).exists()
    
    is_blocked_by_profile_user = BlockedUser.objects.filter(
        blocker=profile_user, 
        blocked=request.user
    ).exists()
    
    if is_blocked_by_profile_user:
        return render(request, 'user_not_found.html')
    
    if query:
        # ✅ Track search query in Redis for collaborative filtering
        try:
            search_key = f"user:search:users:{request.user.id}"
            now_timestamp = int(time.time())
            
            # Store search query with timestamp
            redis_conn.zadd(search_key, {query.lower(): now_timestamp})
            redis_conn.expire(search_key, 60 * 60 * 24 * 30)  # 30 days
            
            # Track search interaction for recommendations
            redis_conn.zadd(
                f"user:searches:{request.user.id}", 
                {f"user:{query}": now_timestamp}
            )
        except Exception as e:
            logger.warning(f"Failed to track user search: {e}")
        
        # Base search query
        users_queryset = AuthUser.objects.filter(
            Q(username__icontains=query) |
            Q(profile__bio__icontains=query) |
            Q(media__description__icontains=query)
        ).select_related('profile').annotate(
            media_count=Count('media'),
            follower_count=Count('followers')
        ).distinct()
        
        # ✅ Get collaborative filtering boosts
        user_scores = {}
        try:
            # Get users the searcher has interacted with
            interacted_users = redis_conn.zrange(
                f"user:interactions:{request.user.id}", 
                0, -1, 
                withscores=True
            )
            
            for user_id_bytes, score in interacted_users:
                try:
                    uid = int(user_id_bytes.decode())
                    user_scores[uid] = score
                except:
                    pass
        except Exception as e:
            logger.warning(f"Failed to get user interaction scores: {e}")
        
        # Convert to list and score
        users_list = list(users_queryset)
        
        # ✅ Score users based on multiple factors
        scored_users = []
        for user in users_list:
            score = 0
            
            # Exact username match boost
            if user.username.lower() == query.lower():
                score += 100
            elif user.username.lower().startswith(query.lower()):
                score += 50
            
            # Bio match boost
            if user.profile.bio and query.lower() in user.profile.bio.lower():
                score += 20
            
            # Collaborative filtering boost
            if user.id in user_scores:
                score += user_scores[user.id] * 10
            
            # Popularity boost (but not too much)
            score += min(user.follower_count * 0.1, 10)
            score += min(user.media_count * 0.05, 5)
            
            scored_users.append((user, score))
        
        # Sort by score
        scored_users.sort(key=lambda x: x[1], reverse=True)
        users = [u for u, _ in scored_users]
    
    # Pagination
    paginator = Paginator(users, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'search_results.html', {
        'page_obj': page_obj,
        'query': query,
        'profile_user': profile_user,
        'is_blocked': is_blocked,
    })

'''
#to search users 
@login_required
@cache_page(60 * 30)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def search_users(request, user_id):

    #query = re.sub(r'\s+', ' ', request.GET.get('q', '')).strip()

    query = request.GET.get('q', '').strip()
    profile_user = get_object_or_404(AuthUser, id=user_id)

    # Initialize an empty queryset to handle cases where the query is empty
    users = AuthUser.objects.none()

    if query:
        # Filter users based on username, profile bio, or media description
        users = AuthUser.objects.filter(
            Q(username__icontains=query) |
            Q(profile__bio__icontains=query) |
            Q(media__description__icontains=query)
        ).distinct()

    # Check if the current user has blocked this profile user
    is_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=profile_user).exists()
    
    # Check if the profile user has blocked the current user
    is_blocked_by_profile_user = BlockedUser.objects.filter(blocker=profile_user, blocked=request.user).exists()
    
    if is_blocked_by_profile_user:
        return render(request, 'user_not_found.html')
    

    # Set up pagination with 100 users per page
    paginator = Paginator(users, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'search_results.html', {
        'page_obj': page_obj, 
        'query': query,
        'profile_user': profile_user,
        'is_blocked': is_blocked,
        })
'''
# ===============================================================
# ENHANCED USER SEARCH WITH COLLABORATIVE FILTERING
# ===============================================================


# =====================================================================
# ENHANCED like_media update which Adds:
#1. Redis tracking for collaborative filtering
#2. Active user tracking
#3. Trending system integration (likes/comments boost trending)
#4. Penalty reversal (positive engagement reduces creator penalties)
#5. Better view tracking consistency
# =====================================================================


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def like_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = request.user
    redis_conn = get_redis_connection("default")

    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)

    # Check if the user has already liked the media
    if user in media.likes.all():
        media.likes.remove(user)
        liked = False
    else:
        media.likes.add(user)
        liked = True

        # --------------------------------------------------
        #  ADD: REDIS VIEW TRACKING (For Collaborative Filtering)
        # --------------------------------------------------
        # If user likes, they've definitely viewed it
        try:
            now_timestamp = int(time.time())
            
            # Track view in Redis (collaborative filtering)
            redis_conn.zadd(f"user:viewed:{user.id}", {media.id: now_timestamp})
            redis_conn.zadd(f"media:viewed_by:{media.id}", {user.id: now_timestamp})
            
            # Set expiry
            redis_conn.expire(f"user:viewed:{user.id}", 60 * 60 * 24 * 30)
            redis_conn.expire(f"media:viewed_by:{media.id}", 60 * 60 * 24 * 30)
            
        except Exception as e:
            logger.warning(f"Redis view tracking failed: {e}")

        # Check if user has a 'view' engagement entry
        view_exists = Engagement.objects.filter(user=user, media=media, engagement_type='view').exists()

        if not view_exists:
            # Increase view count
            Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
            Engagement.objects.create(media=media, user=user, engagement_type='view')

            # Store viewed media ID
            viewed_media = user_hashtag_pref.viewed_media or []
            if media.id not in viewed_media:
                viewed_media.append(media.id)
                user_hashtag_pref.viewed_media = viewed_media[-60:]  # MAX_VIEWED_MEDIA_CACHE
                user_hashtag_pref.save(update_fields=["viewed_media"])

        # --------------------------------------------------
        #  ADD: ACTIVE USER TRACKING
        # --------------------------------------------------
        try:
            now = int(time.time())
            cutoff = now - 3600
            
            redis_conn.zadd("active:users", {user.id: now})
            redis_conn.zremrangebyscore("active:users", 0, cutoff)
        except Exception as e:
            logger.warning(f"Active user tracking failed: {e}")

        # Track engagement with category
        user_hashtag_pref.add_liked_category(media.category)

        # Update liked hashtags
        hashtags_in_description = re.findall(r'#(\w+)', media.description or "")
        for hashtag in hashtags_in_description:
            user_hashtag_pref.liked_hashtags = add_to_fifo_list(
                user_hashtag_pref.liked_hashtags, hashtag
            )
        user_hashtag_pref.save()

        # --------------------------------------------------
        #  ADD: PENALTY REVERSAL (Positive engagement reduces penalties)
        # --------------------------------------------------
        try:
            creator_id = media.user_id
            
            # Check if creator is penalized
            creator_penalty = redis_conn.zscore(f"user:creator_penalty:{user.id}", creator_id)
            
            if creator_penalty and creator_penalty > 0:
                # Reduce penalty by 1 (positive engagement)
                new_penalty = max(0, creator_penalty - 1)
                
                if new_penalty > 0:
                    redis_conn.zadd(f"user:creator_penalty:{user.id}", {creator_id: new_penalty})
                else:
                    # Remove penalty completely if it reaches 0
                    redis_conn.zrem(f"user:creator_penalty:{user.id}", creator_id)
                
                logger.info(f"Reduced creator {creator_id} penalty for user {user.id}: {creator_penalty} → {new_penalty}")
            
            # Also reduce category penalty if exists
            category = getattr(media, 'category', None)
            if category:
                category_penalty = redis_conn.zscore(f"user:category_penalty:{user.id}", category)
                if category_penalty and category_penalty > 0:
                    new_penalty = max(0, category_penalty - 0.5)
                    if new_penalty > 0:
                        redis_conn.zadd(f"user:category_penalty:{user.id}", {category: new_penalty})
                    else:
                        redis_conn.zrem(f"user:category_penalty:{user.id}", category)
        
        except Exception as e:
            logger.warning(f"Penalty reversal failed: {e}")

        # --------------------------------------------------
        #  ADD: TRENDING BOOST (Likes boost trending score)
        # --------------------------------------------------
        # The like itself automatically boosts trending when update_trending_scores runs
        # No action needed here - just documenting the integration

        # Create notification
        if user != media.user:
            Notification.objects.create(
                user=media.user,
                content=f'{user.username} liked your media: '
                        f'<a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                type='like',
                related_user=user,
                related_media=media
            )

    # Handle AJAX requests
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'liked': liked,
            'like_count': media.likes.count(),
            'view_count': media.view_count
        })

    return redirect(request.META.get('HTTP_REFERER', reverse('user_profile:media_detail_view', args=[media.id])))

# =====================================================================
# ENHANCED like_media update which Adds:
#1. Redis tracking for collaborative filtering
#2. Active user tracking
#3. Trending system integration (likes/comments boost trending)
#4. Penalty reversal (positive engagement reduces creator penalties)
#5. Better view tracking consistency
# =====================================================================


# =====================================================================
# ENHANCED comment_media
#comment_media enhancements:
#1.  Redis view tracking (collaborative filtering)
#2.  Database view tracking (if not already viewed)
#3.  Active user tracking
#4.  Hashtag tracking (comments track engaged hashtags)
#5.  Penalty reversal (comment reduces creator penalty by 2)
#6.  Category penalty reversal (comment reduces by 1)
#7.  Better error handling
# =====================================================================


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def comment_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    
    if request.method == 'POST':
        redis_conn = get_redis_connection("default")
        user = request.user
        
        content = request.POST.get('content', '')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        # Transform content to include clickable usernames
        content = make_usernames_clickable(escape(content))

        # --------------------------------------------------
        #  ADD: VIEW TRACKING (Commenting = Viewing)
        # --------------------------------------------------
        # If user comments, they've definitely viewed the media
        try:
            now_timestamp = int(time.time())
            
            # Track view in Redis (collaborative filtering)
            redis_conn.zadd(f"user:viewed:{user.id}", {media.id: now_timestamp})
            redis_conn.zadd(f"media:viewed_by:{media.id}", {user.id: now_timestamp})
            
            # Set expiry
            redis_conn.expire(f"user:viewed:{user.id}", 60 * 60 * 24 * 30)
            redis_conn.expire(f"media:viewed_by:{media.id}", 60 * 60 * 24 * 30)
            
        except Exception as e:
            logger.warning(f"Redis view tracking failed: {e}")
        
        # Track in database
        view_exists = Engagement.objects.filter(
            user=user, media=media, engagement_type='view'
        ).exists()
        
        if not view_exists:
            Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
            Engagement.objects.create(media=media, user=user, engagement_type='view')
            
            # Update viewed media cache
            user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
            viewed_media = user_hashtag_pref.viewed_media or []
            if media.id not in viewed_media:
                viewed_media.append(media.id)
                user_hashtag_pref.viewed_media = viewed_media[-60:]
                user_hashtag_pref.save(update_fields=["viewed_media"])

        # --------------------------------------------------
        #  ADD: ACTIVE USER TRACKING
        # --------------------------------------------------
        try:
            now = int(time.time())
            cutoff = now - 3600
            
            redis_conn.zadd("active:users", {user.id: now})
            redis_conn.zremrangebyscore("active:users", 0, cutoff)
        except Exception as e:
            logger.warning(f"Active user tracking failed: {e}")

        # Create comment
        comment = Comment.objects.create(user=user, media=media, content=content)

        # Process hashtags
        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        # --------------------------------------------------
        #  ADD: TRACK COMMENTED HASHTAGS
        # --------------------------------------------------
        # Track hashtags in comments as positive signal
        try:
            user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
            
            for hashtag in hashtags:
                # Add to viewed/engaged hashtags
                user_hashtag_pref.add_viewed_hashtag([hashtag])
            
            user_hashtag_pref.save()
        except Exception as e:
            logger.warning(f"Hashtag tracking failed: {e}")

        # --------------------------------------------------
        #  ADD: PENALTY REVERSAL (Comments are strong positive signals)
        # --------------------------------------------------
        try:
            creator_id = media.user_id
            
            # Reduce creator penalty more aggressively for comments (2 points vs 1 for likes)
            creator_penalty = redis_conn.zscore(f"user:creator_penalty:{user.id}", creator_id)
            
            if creator_penalty and creator_penalty > 0:
                new_penalty = max(0, creator_penalty - 2)  # Comments reduce by 2
                
                if new_penalty > 0:
                    redis_conn.zadd(f"user:creator_penalty:{user.id}", {creator_id: new_penalty})
                else:
                    redis_conn.zrem(f"user:creator_penalty:{user.id}", creator_id)
                
                logger.info(f"Reduced creator {creator_id} penalty for user {user.id} (comment): {creator_penalty} → {new_penalty}")
            
            # Reduce category penalty
            category = getattr(media, 'category', None)
            if category:
                category_penalty = redis_conn.zscore(f"user:category_penalty:{user.id}", category)
                if category_penalty and category_penalty > 0:
                    new_penalty = max(0, category_penalty - 1)
                    if new_penalty > 0:
                        redis_conn.zadd(f"user:category_penalty:{user.id}", {category: new_penalty})
                    else:
                        redis_conn.zrem(f"user:category_penalty:{user.id}", category)
        
        except Exception as e:
            logger.warning(f"Penalty reversal failed: {e}")

        # Process tagged users
        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)

                # Create notification for tagged user
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{user.username} mentioned you in a comment: <a href="{reverse("user_profile:media_detail_view", args=[media.id])}#{comment.id}">View Comment</a>',
                    type='mention',
                    related_user=user,
                    related_media=media,
                    comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        # Create notification for media owner
        if user != media.user:
            Notification.objects.create(
                user=media.user,
                content=f'{user.username} commented on your media: <a href="{reverse("user_profile:media_detail_view", args=[media.id])}#{comment.id}">View Comment</a>',
                type='comment',
                related_user=user,
                related_media=media,
                comment=comment
            )

        # Redirect with anchor
        return redirect(f"{reverse('user_profile:media_detail_view', args=[media.id])}#{comment.id}")

    # If not POST, redirect to media detail
    return redirect(reverse('user_profile:media_detail_view', args=[media.id]))

# =====================================================================
# ENHANCED comment_media
#comment_media enhancements:
#1.  Redis view tracking (collaborative filtering)
#2.  Database view tracking (if not already viewed)
#3.  Active user tracking
#4.  Hashtag tracking (comments track engaged hashtags)
#5.  Penalty reversal (comment reduces creator penalty by 2)
#6.  Category penalty reversal (comment reduces by 1)
#7.  Better error handling
# =====================================================================


#delete comments
@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def delete_user_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    media = comment.media
    if request.user == comment.user or request.user == media.user:
        comment.delete()
        return redirect('user_profile:media_detail_view', media_id=media.id)
    return redirect('user_profile:media_detail_view', media_id=media.id)



@login_required
def like_audio(request, audio_id):
    audio = get_object_or_404(Audio, id=audio_id)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

    # Check if the user has already liked the audio
    if request.user in audio.likes.all():
        audio.likes.remove(request.user)
        liked = False
    else:
        audio.likes.add(request.user)
        liked = True

        # Update the liked hashtags list based on the audio description
        hashtags_in_description = re.findall(r'#(\w+)', audio.description)
        for hashtag in hashtags_in_description:
            user_hashtag_pref.liked_hashtags = add_to_fifo_list(user_hashtag_pref.liked_hashtags, hashtag)

        user_hashtag_pref.save()

        # Create a clickable notification for the audio owner
        if request.user != audio.user:  # Avoid notifying the audio owner if they like their own audio
            Notification.objects.create(
                user=audio.user,
                content=f'{request.user.username} liked your audio: <a href="{reverse("user_profile:voices", args=[audio.user.id])}">View Audio</a>',
                type='like',
                related_user=request.user,
                related_audio=audio
            )

    # Handle AJAX requests to return like status and like count
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'like_count': audio.likes.count()})

    # Redirect back to the referring page or to the audio detail view
    return redirect(request.META.get('HTTP_REFERER', reverse('user_profile:voices', args=[audio.user.id])))



@login_required
def comment_audio(request, audio_id):
    audio = get_object_or_404(Audio, id=audio_id)

    if request.method == 'POST':
        content = request.POST.get('content', '')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        # Transform content to include clickable usernames and sanitize it
        content = make_usernames_clickable(escape(content))

        # Create the comment associated with the audio
        comment = Comment.objects.create(user=request.user, audio=audio, content=content)

        # Process hashtags
        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        # Process tagged usernames and create notifications for tagged users
        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)

                # Create a clickable notification for the tagged user
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{request.user.username} mentioned you in a comment: <a href="{reverse("user_profile:voices", args=[audio.user.id])}#{comment.id}">View Comment</a>',
                    type='mention',
                    related_user=request.user,
                    related_audio=audio,
                    comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        # Create a notification for the audio owner
        if request.user != audio.user:  # Avoid notifying the audio owner if they are commenting on their own audio
            Notification.objects.create(
                user=audio.user,
                content=f'{request.user.username} commented on your audio: <a href="{reverse("user_profile:voices", args=[audio.user.id])}#{comment.id}">View Comment</a>',
                type='comment',
                related_user=request.user,
                related_audio=audio,
                comment=comment
            )

        # If AJAX request, return the comment details as JSON
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'comment_id': comment.id,
                'content': comment.content,
                'user': request.user.username,
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'like_count': audio.likes.count(),
                'comment_count': audio.comments.count()
            })

        # Redirect to the audio page with the new comment's anchor
        return redirect(f"{reverse('user_profile:voices', args=[audio.user.id])}#{comment.id}")

    # If not POST, fallback to redirecting to the audio detail page
    return redirect(reverse('user_profile:voices', args=[audio.user.id]))


@login_required
def delete_user_audio_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    # Ensure the comment is linked to audio
    if not comment.audio:
        return redirect('user_profile:voices', user_id=request.user.id)

    audio = comment.audio
    if request.user == comment.user or request.user == audio.user:
        comment.delete()

    # Redirect back to the voices page for the user
    return redirect(reverse('user_profile:voices', args=[audio.user.id]))



@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def media_detail_view(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user  # The owner of the media
    user_id = getattr(request.user, "pk", None)  #  safe for anonymous

    # --- Bot preview (disabled in your code) ---
    if is_bot_request(request):
        description = make_usernames_clickable(media.description or "")
        return bot_meta_response("meta_preview.html", {
            "media": media,
            "title": f"{user.username} on Socyfie",
            "description": description,
            "image_url": media.file.url if media.file else "",
            "url": request.build_absolute_uri(),
        })

    # Block checks
    is_blocked_by_media_owner = BlockedUser.objects.filter(
        blocker=user, blocked_id=user_id
    ).exists() if user_id else False

    has_blocked_media_owner = BlockedUser.objects.filter(
        blocker_id=user_id, blocked=user
    ).exists() if user_id else False

    if is_blocked_by_media_owner:
        return render(request, "user_not_found.html")

    # Follow / buddy checks
    is_following = Follow.objects.filter(
        follower_id=user_id, following=user
    ).exists() if user_id else False

    is_buddy = Buddy.objects.filter(
        user=user, buddy_id=user_id
    ).exists() if user_id else False

    # Privacy checks
    if media.is_private and not is_buddy and request.user != user:
        return render(request, "private_upload.html")

    if (media.is_private or user.profile.is_private) and not is_following and request.user != user:
        return render(request, "private_upload.html")

    # Older uploads
    older_uploads = Media.objects.filter(user=user, created_at__lt=media.created_at)

    if request.user != user and not is_buddy:
        older_uploads = older_uploads.filter(is_private=False)

    older_uploads = older_uploads.order_by("-created_at")

    paginator = Paginator(older_uploads, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Engagement tracking
    if user_id:
        if not Engagement.objects.filter(user_id=user_id, media=media, engagement_type="view").exists():
            Media.objects.filter(pk=media.pk).update(view_count=F("view_count") + 1)
            Engagement.objects.create(media=media, user_id=user_id, engagement_type="view")
    else:
        # Guests still increase view count
        Media.objects.filter(pk=media.pk).update(view_count=F("view_count") + 1)

    # Hashtag preferences
    if user_id:
        user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user_id=user_id)
        liked_hashtags = user_hashtag_pref.liked_hashtags
        not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
        viewed_hashtags = user_hashtag_pref.viewed_hashtags
        search_hashtags = user_hashtag_pref.search_hashtags
        liked_categories = user_hashtag_pref.liked_categories
        viewed_media = user_hashtag_pref.viewed_media

        if media.id not in viewed_media:
            viewed_media.append(media.id)
            user_hashtag_pref.viewed_media = viewed_media[-MAX_VIEWED_MEDIA_CACHE:]
            user_hashtag_pref.save(update_fields=["viewed_media"])

        description_hashtags = re.findall(r"#(\w+)", media.description or "")
        user_hashtag_pref.add_viewed_hashtag(description_hashtags)
    else:
        liked_hashtags = []
        not_interested_hashtags = []
        viewed_hashtags = []
        search_hashtags = []
        liked_categories = []
        viewed_media = []

    # Description
    description = make_usernames_clickable(media.description or "")

    context = {
        "media": media,
        "description": description,
        "is_following": is_following,
        "is_buddy": is_buddy,
        "has_blocked_media_owner": has_blocked_media_owner,
        "is_blocked_by_media_owner": is_blocked_by_media_owner,
        "page_obj": page_obj,
        "liked_hashtags": liked_hashtags,
        "not_interested_hashtags": not_interested_hashtags,
        "viewed_hashtags": viewed_hashtags,
        "search_hashtags": search_hashtags,
        "liked_categories": liked_categories,
        "viewed_media": viewed_media,
    }

    return render(request, "media_detail.html", context)




@login_required
@cache_page(60 * 8)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def profile_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(notifications, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'profile_notifications.html', {'page_obj': page_obj})



@login_required
@cache_control(private=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def edit_profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    profile, created = Profile.objects.get_or_create(user=profile_user)

    # Initialize forms
    profile_form = ProfileForm(instance=profile)
    username_form = UsernameUpdateForm(initial={'new_username': profile_user.username})
    category_form = CategorySelectionForm(instance=profile)  # Category selection form
    country_form = CountrySelectionForm(instance=profile)

    if request.method == 'POST':
        if 'save_changes' in request.POST:  # Handle profile updates
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)

            if profile_form.is_valid():
                saved_profile = profile_form.save()  # quick save
                #  Launch Celery task asynchronously
                process_profile_images.delay(saved_profile.id)
                messages.success(request, 'Profile update is being processed!')
                return redirect('user_profile:profile', user_id=user_id)
            else:
                messages.error(request, 'Error updating your profile')

        elif 'update_username' in request.POST:  # Handle username updates
            username_form = UsernameUpdateForm(request.POST)

            if username_form.is_valid():
                new_username = username_form.cleaned_data['new_username']
                if new_username != profile_user.username:  # Only update if the username changed
                    profile_user.username = new_username
                    profile_user.save()
                messages.success(request, 'Username updated successfully!')
                return redirect('user_profile:profile', user_id=user_id)
            else:
                messages.error(request, 'Error updating your username')

        elif 'update_category' in request.POST:  # Handle category selection updates
            category_form = CategorySelectionForm(request.POST, instance=profile)

            if category_form.is_valid():
                category_form.save()
                messages.success(request, 'Category updated successfully!')
                return redirect('user_profile:profile', user_id=user_id)
            else:
                messages.error(request, 'Error updating your category')

        elif 'update_country' in request.POST:
            country_form = CountrySelectionForm(
                request.POST,
                instance=profile
            )

            if country_form.is_valid():
                country_form.save()
                messages.success(request, 'Country updated successfully!')
                return redirect(
                    'user_profile:profile',
                    user_id=user_id
                )
            else:
                messages.error(request, 'Error updating your country')


    return render(request, 'edit_profile.html', {
        'form': profile_form,
        'username_form': username_form,
        'category_form': category_form,  # Include the category form
        'country_form': country_form,

        'profile_user': profile_user
    })




CATEGORY_CHOICES = [
    ('media_journalism', 'Media and Journalism'),
    ('entertainment', 'Entertainment'),
    ('sports_fitness', 'Sports and Fitness'),
    ('creators_influencers', 'Creators and Influencers'),
    ('education_learning', 'Education and Learning'),
    ('business_entrepreneurship', 'Business and Entrepreneurship'),
    ('art_design', 'Art and Design'),
    ('social_causes', 'Social Causes and Activism'),
    ('tech_science', 'Technology and Science'),
    ('health_wellness', 'Health and Wellness'),
    ('hobbies_interests', 'Hobbies and Interests'),
    ('government_politics', 'Government and Politics'),
    ('religious_spiritual', 'Religious and Spiritual'),
    ('travel_adventure', 'Travel and Adventure'),
    ('comedy_memes', 'Comedy and Memes'),
    ('gaming', 'Gaming'),
    ('finance', 'Finance'),
]

@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def update_category(request):
    profile = request.user.profile  # Access the Profile instance for the logged-in user

    if request.method == 'POST':
        form = CategorySelectionForm(request.POST, instance=profile)  # Bind the form to the Profile model
        if form.is_valid():
            form.save()  # Save the updated category to the Profile instance

            # Handle AJAX requests
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'category': form.cleaned_data['category']  # Return the readable category name
                })

            messages.success(request, "Your category has been updated.")
            return redirect('user_profile:profile', user_id=request.user.id)  # Non-AJAX redirect

    else:
        form = CategorySelectionForm(instance=profile)  # Populate the form with the current profile data

    # Handle GET requests for AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'category': profile.category
        })

    return render(request, 'edit_profile.html', {'form': form})




@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def update_country(request):
    profile = request.user.profile

    if request.method == 'POST':
        form = CountrySelectionForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()

            # AJAX request
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'country': str(form.cleaned_data['country'])
                })

            messages.success(request, "Your country has been updated.")
            return redirect(
                'user_profile:profile',
                user_id=request.user.id
            )

    else:
        form = CountrySelectionForm(instance=profile)

    # AJAX GET request
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'country': str(profile.country) if profile.country else ''
        })

    return render(request, 'edit_profile.html', {'form': form})



@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def fetch_categories(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'categories': CATEGORY_CHOICES  # Return the choices as a list
        })
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def save_bio(request):
    profile = request.user.profile  # Assuming Profile is related to the user

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Bio updated successfully!")
        else:
            messages.error(request, "There was an error updating your bio.")

    return redirect('user_profile:profile', user_id=request.user.id)


#____________________________________________________________________
#
#delete uploaded media with redish upgrads 
#
#--------------------------------------------------------------------


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def delete_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)

    # Optional: ensure only owner can delete
    if media.user != request.user:
        return redirect('user_profile:profile', user_id=request.user.id)

    active_story = Story.objects.filter(media=media).first()

    if request.method == 'POST':

        # ---------------------------
        # DELETE FILE FROM STORAGE
        # ---------------------------
        if media.file:
            media.file.delete(save=False)

        # ---------------------------
        # REDIS CLEANUP
        # ---------------------------
        try:
            redis = get_redis_connection("default")

            # Remove creator mapping
            redis.delete(f"media:creator:{media_id}")

            # Remove from trending ZSET
            redis.zrem("media:trending", media_id)

        except Exception as e:
            # Do not block deletion if Redis fails
            logger.warning(f"Redis cleanup failed for media {media_id}: {e}")

        # ---------------------------
        # DELETE DATABASE RECORD
        # ---------------------------
        media.delete()

        # ---------------------------
        # DELETE ACTIVE STORY IF EXISTS
        # ---------------------------
        if active_story:
            active_story.delete()

        return redirect('user_profile:profile', user_id=request.user.id)

    context = {'media': media}
    return render(request, 'user_profile/delete_media.html', context)

#____________________________________________________________________
#
#delete uploaded media with redish upgrads
#
#--------------------------------------------------------------------

@login_required
def delete_audio(request, audio_id):
    audio = get_object_or_404(Audio, id=audio_id)

    # Ensure only the audio owner or an admin can delete the audio
    if request.user != audio.user and not request.user.is_staff:
        return redirect('user_profile:voices', user_id=audio.user.id)

    if request.method == 'POST':
        # Delete the audio file from storage and remove the audio instance
        audio.file.delete(save=False)
        audio.delete()

        # Redirect to the user's profile or voices page after deletion
        return redirect('user_profile:voices', user_id=audio.user.id)

    # Render the confirmation page for deletion
    context = {'audio': audio}
    return render(request, 'user_profile/delete_audio.html', context)

#-----------------------------------------------------------------------
#
#
#-----------------------------------------------------------------------

'''
@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def not_interested(request, media_id: int):
    try:
        media = get_object_or_404(Media, id=media_id)
        user = request.user

        user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=user)

        # ---------------------------
        # Store in DB (existing logic)
        # ---------------------------
        user_hashtag_pref.add_not_interested_media(media_id)

        hashtags = re.findall(r'#(\w+)', media.description or "")

        for hashtag in hashtags:
            user_hashtag_pref.not_interested_hashtags = add_to_fifo_list(
                user_hashtag_pref.not_interested_hashtags,
                hashtag
            )

        user_hashtag_pref.save()

        # ---------------------------
        # Store in Redis (NEW)
        # ---------------------------
        redis = get_redis_connection("default")

        # Add media to Redis set
        redis.sadd(f"user:not_interested:media:{user.id}", media_id)

        # Add creator to Redis set (if available)
        creator_id = getattr(media, "creator_id", None)
        if creator_id:
            redis.sadd(f"user:not_interested:creator:{user.id}", creator_id)

        # ---------------------------
        # Remove immediately from recommendations (NEW)
        # ---------------------------
        redis.zrem(f"user:reco:{user.id}", media_id)

        # ---------------------------
        # Response
        # ---------------------------
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': 'Media and preferences updated'
            })

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    except Exception as e:
        return HttpResponse('Error occurred', status=500)
'''


@login_required
@require_POST
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def not_interested(request, media_id: int):
    """
    Handles "Not Interested" action.

    - Updates Django DB (media + hashtags FIFO)
    - Updates Redis for recommendation engine
    - Updates Redis collaborative filtering keys
    - Removes media immediately from recommendation ZSET
    - NEW: Tracks penalties (creator/category/hashtag)
    - NEW: Detects similar media via collaborative signals
    - NEW: Clears seen feed cache
    """

    try:
        user = request.user

        # ---------------------------
        # Validate media
        # ---------------------------
        media = get_object_or_404(Media, id=media_id)

        # ---------------------------
        # Django Model Updates (ORIGINAL LOGIC PRESERVED)
        # ---------------------------
        user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=user)

        user_hashtag_pref.add_not_interested_media(media_id)

        hashtags = re.findall(r'#(\w+)', media.description or "")

        for hashtag in hashtags:
            user_hashtag_pref.not_interested_hashtags = add_to_fifo_list(
                user_hashtag_pref.not_interested_hashtags,
                hashtag
            )

        user_hashtag_pref.save()

        # ---------------------------
        # Redis Updates (ORIGINAL KEYS PRESERVED)
        # ---------------------------
        redis_conn = get_redis_connection("default")

        redis_conn.sadd(f"user:not_interested:media:{user.id}", media_id)
        redis_conn.expire(f"user:not_interested:media:{user.id}", 60*60*24*30)  # 30 days


        creator_id = getattr(media, "creator_id", None) or media.user_id
        if creator_id:
            redis_conn.sadd(f"user:not_interested:creator:{user.id}", creator_id)
            redis_conn.expire(f"user:not_interested:creator:{user.id}", 60*60*24*30)  # 30 days


        # Collaborative Filtering Keys
        redis_conn.sadd(f"user:ni:media:{user.id}", media_id)
        redis_conn.expire(f"user:ni:media:{user.id}", 60*60*24*30)  # ✅ ADD THIS

        creator_key = f"media:creator:{media_id}"
        if not redis_conn.exists(creator_key):
            redis_conn.set(creator_key, media.user_id)

        redis_conn.sadd(f"user:ni:creator:{user.id}", media.user_id)
        redis_conn.expire(f"user:ni:creator:{user.id}", 60*60*24*30)  # ✅ ADD THIS

        # ---------------------------
        #  NEW: PENALTY TRACKING
        # ---------------------------

        # Creator penalty (90 days)
        redis_conn.zincrby(f"user:creator_penalty:{user.id}", 1, media.user_id)
        redis_conn.expire(f"user:creator_penalty:{user.id}", 60 * 60 * 24 * 90)

        # Category penalty (60 days)
        category = getattr(media, 'category', None)
        if category:
            redis_conn.zincrby(f"user:category_penalty:{user.id}", 1, category)
            redis_conn.expire(f"user:category_penalty:{user.id}", 60 * 60 * 24 * 60)

        # Hashtag penalties (30 days)
        if hashtags:
            for hashtag in hashtags:
                redis_conn.zincrby(f"user:hashtag_penalty:{user.id}", 1, hashtag)
            redis_conn.expire(f"user:hashtag_penalty:{user.id}", 60 * 60 * 24 * 30)

        # ---------------------------
        #  NEW: FIND SIMILAR MEDIA
        # ---------------------------
        try:
            viewers = redis_conn.zrange(f"media:viewed_by:{media_id}", 0, 49)
            similar_counter = {}

            for viewer_bytes in viewers:
                viewer_id = int(viewer_bytes.decode())
                if viewer_id == user.id:
                    continue

                their_viewed = redis_conn.zrange(f"user:viewed:{viewer_id}", 0, -1)
                for other_media_bytes in their_viewed:
                    other_id = int(other_media_bytes.decode())
                    if other_id != media_id:
                        similar_counter[other_id] = similar_counter.get(other_id, 0) + 1

            if similar_counter:
                sorted_similar = sorted(
                    similar_counter.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:20]

                now = int(time.time())
                for similar_id, _ in sorted_similar:
                    redis_conn.zadd(f"user:similar_ni:{user.id}", {similar_id: now})

                redis_conn.expire(f"user:similar_ni:{user.id}", 60 * 60 * 24 * 30)

        except Exception:
            pass

        # ---------------------------
        # Remove immediately from recommendations (ORIGINAL LOGIC PRESERVED)
        # ---------------------------
        redis_conn.zrem(f"user:reco:{user.id}", media_id)

        # ---------------------------
        #  NEW: CLEAR FEED CACHE
        # ---------------------------
        redis_conn.delete(f"user:seen_feed:{user.id}")

        logger.info(f"User {user.id} marked media {media_id} as not interested")

        # ---------------------------
        # Response Handling (ORIGINAL BEHAVIOR PRESERVED)
        # ---------------------------
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': 'Media and preferences updated'
            })

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    except Exception as e:
        logger.exception(f"Error in not_interested: {e}")

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'error': 'An error occurred',
                'details': str(e)
            }, status=500)

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))


@require_POST
def undo_not_interested(request):
    """
    Undo a "not interested" marking.
    
    Removes from both Django model AND Redis cache.
    """
    try:
        media_id = request.POST.get('media_id')
        user = request.user
        
        if not user.is_authenticated:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        
        if not media_id:
            return JsonResponse({'error': 'Missing media_id'}, status=400)
        
        # 1. Update Django model
        try:
            pref_obj = UserHashtagPreference.objects.get(user=user)
            if pref_obj.not_interested_media and int(media_id) in pref_obj.not_interested_media:
                pref_obj.not_interested_media.remove(int(media_id))
                pref_obj.save(update_fields=['not_interested_media'])
        except UserHashtagPreference.DoesNotExist:
            pass  # No preferences to update
        
        # 2. Update Redis cache
        redis_conn = get_redis_connection("default")
        redis_conn.srem(f"user:ni:media:{user.id}", media_id)
        
        # Note: Don't remove from ni:creator as user might still have
        # other media from this creator marked as not interested
        
        logger.info(f"User {user.id} undid not interested for media {media_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Removed from not interested'
        })
        
    except Exception as e:
        logger.exception(f"Error undoing not interested: {e}")
        return JsonResponse({
            'error': 'An error occurred',
            'details': str(e)
        }, status=500)



#-----------------------------------------------------------------------
#
#
#-----------------------------------------------------------------------

@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def report_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

    if request.user not in media.reported_by.all():
        media.reported_by.add(request.user)
        media.report_count += 1
        media.save()

        # Add to "Not Interested" queue when reporting
        hashtags = re.findall(r'#(\w+)', media.description)
        for hashtag in hashtags:
            user_hashtag_pref.not_interested_hashtags = add_to_fifo_list(user_hashtag_pref.not_interested_hashtags, hashtag)
        
        user_hashtag_pref.save()

        # Create admin notification if report count exceeds 500
        if media.report_count > 50:
            AdminNotification.objects.create(media=media)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Media reported'})

    return redirect(request.META.get('HTTP_REFERER', 'user_profile:media_detail_view'), media_id=media.id)


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def save_upload(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    profile = get_object_or_404(Profile, user=request.user)

    if media in profile.saved_uploads.all():
        profile.saved_uploads.remove(media)
        saved = False
    else:
        profile.saved_uploads.add(media)
        saved = True

    profile.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'saved': saved})

    return redirect(request.META.get('HTTP_REFERER', 'user_profile:saved_uploads'))


@login_required
@cache_page(60 * 30)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def saved_uploads(request):
    profile = get_object_or_404(Profile, user=request.user)
    saved_media = profile.saved_uploads.all().order_by('-created_at')

    paginator = Paginator(saved_media, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'saved.html', {
        'page_obj': page_obj,
    })


#@login_required
# def add_story(request):
#     if request.method == 'POST':
#         file = request.FILES.get('file')
#         description = request.POST.get('description')
        
#         media = Media.objects.create(
#             user=request.user,
#             file=file,
#             description=description,
#             media_type=file.content_type.split('/')[0],
#             is_private = True
#         )
        
#         story = Story.objects.create(user=request.user, media=media)
        
#         # Redirect to the `view_story` page with the new story's id
#         return redirect('user_profile:view_story', story_id=story.id)

#     return render(request, 'add_story.html')

'''
@login_required
def add_story(request):
    if request.method == 'POST':
        file = request.FILES.get('file')
        user_description = request.POST.get('description', '')

        # Prepend "story " to the description provided by the user
        description = f"story {user_description.strip()}" if user_description else "story "

        media = Media.objects.create(
            user=request.user,
            file=file,
            description=description,
            media_type=file.content_type.split('/')[0],
            is_private=True
        )
        
        story = Story.objects.create(user=request.user, media=media)
        
        # Redirect to the `view_story` page with the new story's id
        return redirect('user_profile:view_story', story_id=story.id)

    return render(request, 'add_story.html')

'''

@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def add_story(request):
    if request.method == 'POST':
        file = request.FILES.get('file')
        user_description = request.POST.get('description', '')

        # Prepend "story " to the description provided by the user
        description = f"story {user_description.strip()}" if user_description else "story "

        if file:
            content_type = file.content_type

            # Allow only image uploads
            if content_type.startswith('image/'):
                media = Media.objects.create(
                    user=request.user,
                    file=file,
                    description=description,
                    media_type='image',
                    is_private=True
                )
                
                story = Story.objects.create(user=request.user, media=media)
                
                # Redirect to the `view_story` page with the new story's id
                return redirect('user_profile:view_story', story_id=story.id)

            elif content_type.startswith('video/'):
                # Display a message if a video is uploaded
                messages.error(request, "Video uploads are not available yet.")
                return redirect('user_profile:add_story')

        # If no file was uploaded or an unsupported file type was used
        messages.error(request, "Invalid or missing file. Please upload an image.")
    
    return render(request, 'add_story.html')



@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def view_story(request, story_id):
    # Fetch the current story
    story = get_object_or_404(Story, id=story_id)
    
    if story.is_expired():
        story.media.delete()
        # return render(request, 'story_expired.html')
        return redirect('user_profile:profile', user_id=request.user.id)

    # Increment view count and track viewers
    story.media.view_count += 1
    story.media.save()
    story.media.tags.add(request.user)

    # Fetch all stories by the same user
    user_stories = Story.objects.filter(media__user=story.media.user).order_by('created_at')

    # Get the index of the current story
    current_index = list(user_stories).index(story)
    
    # Determine previous and next stories
    prev_story = user_stories[current_index - 1] if current_index > 0 else None
    next_story = user_stories[current_index + 1] if current_index < len(user_stories) - 1 else None


    # if not next_story and not prev_story:
    #     return redirect('user_profile:profile', user_id=story.media.user.id)

    return render(request, 'view_story.html', {
        'story': story,
        'prev_story': prev_story,
        'next_story': next_story,
        'story_duration': 20,  # 20 seconds
        'redirect_to_profile': not prev_story and not next_story,  # Flag to redirect to profile
    })


"""
@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def view_story(request, story_id):
    # Fetch the story object, 404 if not found
    story = get_object_or_404(Story, id=story_id)

    # If the story has expired, delete the media and redirect to profile
    if story.is_expired():
        try:
            # This will delete the file from storage (R2/S3) if `file.delete()` is called
            if story.media:
                story.media.file.delete(save=False)
                story.media.delete()
        except Exception as e:
            print(f"Error deleting expired media: {e}")
        
        return redirect('user_profile:profile', user_id=request.user.id)

    # Increment view count and associate current user as a viewer (tag)
    story.media.view_count = (story.media.view_count or 0) + 1
    story.media.save(update_fields=["view_count"])
    story.media.tags.add(request.user)

    # Get all non-expired stories from the same user, ordered by creation time
    user_stories = Story.objects.filter(
        media__user=story.media.user,
        media__isnull=False
    ).order_by('created_at')

    # Convert queryset to list for indexing
    user_stories_list = list(user_stories)
    try:
        current_index = user_stories_list.index(story)
    except ValueError:
        return redirect('user_profile:profile', user_id=request.user.id)

    # Determine previous and next stories
    prev_story = user_stories_list[current_index - 1] if current_index > 0 else None
    next_story = user_stories_list[current_index + 1] if current_index < len(user_stories_list) - 1 else None

    return render(request, 'view_story.html', {
        'story': story,
        'prev_story': prev_story,
        'next_story': next_story,
        'story_duration': 20,  # seconds
        'redirect_to_profile': not prev_story and not next_story,
    })
"""

#_______________________________________________________________
#
#_______________________________________________________________

'''
@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def toggle_privacy(request):
    profile = request.user.profile
    profile.is_private = not profile.is_private
    profile.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_private': profile.is_private})
    
    return redirect('user_profile:profile', user_id=request.user.id)
'''

@login_required
@require_POST  #  Security: Only POST requests
@cache_control(private=True, max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def toggle_privacy(request):
    """
    Toggle user profile privacy with instant cache updates
    
    Privacy Rule: If user profile is private → all their media removed from trending
    """
    profile = request.user.profile
    profile.is_private = not profile.is_private
    profile.save()
    
    # ✅ INSTANT CACHE UPDATE
    try:
        redis_conn = get_redis_connection("default")
        
        if profile.is_private:
            # User just became private - remove ALL their media from trending
            from service_auth.user_profile.models import Media
            
            user_media_ids = Media.objects.filter(
                user=request.user
            ).values_list('id', flat=True)
            
            if user_media_ids:
                removed = redis_conn.zrem(
                    TRENDING_ZSET_KEY,
                    *[str(mid) for mid in user_media_ids]
                )
                logger.info(
                    f"User {request.user.id} set profile PRIVATE. "
                    f"Removed {removed} media from trending cache instantly"
                )
        else:
            # User became public - media can now appear in trending (if not individually private)
            logger.info(
                f"User {request.user.id} set profile PUBLIC. "
                f"Media can appear in trending (will be added in next update)"
            )
    
    except Exception as e:
        logger.error(f"Error updating trending cache on profile privacy toggle: {e}")
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_private': profile.is_private})
    
    return redirect('user_profile:profile', user_id=request.user.id)
 



@login_required
@require_POST  #  Security: Only POST requests
@cache_control(private=True, max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def toggle_media_privacy(request, media_id):
    """
    Toggle individual media privacy with instant cache updates
    
    Privacy Rule: If media is private → removed from trending, visible only to buddy list
    """
    from service_auth.user_profile.models import Media
    
    media = get_object_or_404(Media, id=media_id, user=request.user)
 
    # Toggle the privacy status
    media.is_private = not media.is_private
    media.save()
    
    #  INSTANT CACHE UPDATE
    try:
        redis_conn = get_redis_connection("default")
        
        if media.is_private:
            # Media just became private - remove from trending instantly
            removed = redis_conn.zrem(TRENDING_ZSET_KEY, str(media.id))
            logger.info(
                f"Media {media.id} set PRIVATE. "
                f"Removed from trending cache instantly: {removed}"
            )
        else:
            # Media became public - can now appear in trending (if user profile is public)
            user_is_public = not request.user.profile.is_private
            logger.info(
                f"Media {media.id} set PUBLIC. "
                f"Can appear in trending: {user_is_public} (user profile public)"
            )
    
    except Exception as e:
        logger.error(f"Error updating trending cache on media privacy toggle: {e}")
 
    # Return the new privacy status as JSON
    return JsonResponse({'is_private': media.is_private})
 
#_______________________________________________________________
#
#_______________________________________________________________

@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def add_to_buddy(request, user_id):
    """Add a user to the current user's buddy list."""
    user_to_add = get_object_or_404(AuthUser, id=user_id)
    
    # Ensure the user is following the current user before adding to buddy list (custom rule)
    Buddy.objects.get_or_create(user=request.user, buddy=user_to_add)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'added_to_buddy'})
    
    return redirect('user_profile:buddy_list')

    

@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def buddy_list(request):
    """Display all users in the current user's buddy list."""
    buddies = Buddy.objects.filter(user=request.user).select_related('buddy')

    #buddy_users = [b.buddy for b in buddies]  # Get the actual User objects
    #return render(request, 'buddy_list.html', {'buddy_users': buddy_users})

    return render(request, 'buddy_list.html', {'buddies': buddies})


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def remove_from_buddy_list(request, user_id):
    """Remove a user from the current user's buddy list."""
    user_to_remove = get_object_or_404(AuthUser, id=user_id)
    buddy_relationship = Buddy.objects.filter(user=request.user, buddy=user_to_remove).first()

    if buddy_relationship:
        buddy_relationship.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'removed_from_buddy'})

    return redirect('user_profile:buddy_list')



# _______________________
# function for sitemap implementaion
#________________________


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def profile_detail(request, username):
    user = get_object_or_404(AuthUser, username=username)
    return profile(request, user_id=user.id)  # Call your existing profile() view


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def media_detail(request, username, media_id):
    user = get_object_or_404(AuthUser, username=username)
    media = get_object_or_404(Media, id=media_id, user=user)
    return media_detail_view(request, media_id=media.id)  # reuse existing logic

#_____________________
#
#view tracking using track_media_view util

@require_POST
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def track_media_view(request, media_id):
    user = request.user
    try:
        media = Media.objects.get(id=media_id)
    except Media.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Media not found'}, status=404)

    # Prevent duplicates in Engagement
    engagement, created = Engagement.objects.get_or_create(
        media=media,
        user=user,
        engagement_type='view'
    )

    if created:
        # Use model method to update viewed_media (limit handled in model)
        pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        pref.add_viewed_media([media.id])

        return JsonResponse({'status': 'success', 'message': 'View recorded'})
    else:
        return JsonResponse({'status': 'exists', 'message': 'View already recorded'})

#
#
#______________________
#


#
#__________________________
#for directly sharing media from teh gallery without opening the app
#for directly sharing, taking the user to the upload form 
@csrf_exempt
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def share_upload(request):
    """
    Handles media shared directly to the PWA via share_target.
    Supports both: 
      - Files (from Gallery, Files, WhatsApp, etc.)
      - Text/URLs (from Chrome, Google, etc.)
    """

    if request.method == "POST":
        file = request.FILES.get("file")
        text = request.POST.get("text", "")
        url = request.POST.get("url", "")
        prefill_description = text or url

        # If 'description' already submitted from form (final upload step)
        if "description" in request.POST:
            form = MediaForm(request.POST, request.FILES)
            if form.is_valid():
                media = form.save(commit=False)
                media.user = request.user
                media.media_type = "image" if file and file.content_type.startswith("image/") else "video"
                media.is_processed = False
                media.save()
                form.save_m2m()

                # Save temp file for Celery (only if file exists)
                if file:
                    ext = os.path.splitext(file.name)[1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
                        for chunk in file.chunks():
                            temp.write(chunk)
                        temp_file_path = temp.name

                    # Offload processing
                    process_media_upload.delay(
                        media.id,
                        temp_file_path,
                        file.name,
                        media.media_type,
                        request.POST.get("filter") if media.media_type == "image" else None
                    )

                # Handle mentions
                tagged_usernames = set(re.findall(r"@(\w+)", media.description))
                for username in tagged_usernames:
                    try:
                        tagged_user = AuthUser.objects.get(username=username)
                        if tagged_user != request.user:
                            Notification.objects.create(
                                user=tagged_user,
                                content=f'{request.user.username} mentioned you in a media description: '
                                        f'<a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                                type="mention",
                                related_user=request.user,
                                related_media=media,
                            )
                    except AuthUser.DoesNotExist:
                        pass

                return redirect("user_profile:following_media", media_id=media.id)

            # Form invalid → show again
            return render(
                request,
                "user_profile/upload.html",
                {
                    "form": form,
                    "prefill_text": prefill_description,
                    "shared_file": {"name": file.name, "content": base64.b64encode(file.read()).decode("utf-8")} if file else None
                },
            )

        # First render: show form
        shared_file = None
        if file:
            shared_file = {
                "name": file.name,
                "content": base64.b64encode(file.read()).decode("utf-8"),
            }

        form = MediaForm(initial={"description": prefill_description})
        return render(
            request,
            "user_profile/upload.html",
            {"form": form, "prefill_text": prefill_description, "shared_file": shared_file},
        )

    # GET or others → normal upload
    return redirect("user_profile:upload_media")


from bs4 import BeautifulSoup
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def get_shared_file(request):
    """
    Dual-purpose endpoint:
    1. /get-shared-file/?url=... → fetch OpenGraph or infer preview.
    2. Otherwise → return session-based shared file + prefill text.
    """
    url_param = request.GET.get("url")

    # --- CASE 1: Preview request ---
    if url_param:
        try:
            if not url_param.startswith("http"):
                return JsonResponse({"error": "Invalid URL"}, status=400)

            headers = {"User-Agent": "Mozilla/5.0 (compatible; OpenGraphFetcher/1.0)"}
            resp = requests.get(url_param, timeout=6, headers=headers)
            content_type = resp.headers.get("Content-Type", "")

            # --- CASE A: Direct media file (no HTML) ---
            if any(t in content_type for t in ["image", "video"]):
                return JsonResponse({
                    "link_preview": {
                        "url": url_param,
                        "title": url_param.split("/")[-1],
                        "description": "",
                        "image": url_param if "image" in content_type else "",
                        "video": url_param if "video" in content_type else ""
                    }
                })

            # --- CASE B: YouTube / youtu.be links ---
            if "youtube.com" in url_param or "youtu.be" in url_param:
                match = re.search(r"(v=|youtu\.be/)([^&?/]+)", url_param)
                video_id = match.group(2) if match else None
                if video_id:
                    return JsonResponse({
                        "link_preview": {
                            "url": url_param,
                            "title": "YouTube Video",
                            "description": "",
                            "video": f"https://www.youtube.com/embed/{video_id}",
                            "image": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                        }
                    })

            # --- CASE C: Normal HTML page with OpenGraph tags ---
            soup = BeautifulSoup(resp.text, "html.parser")
            def safe_content(tag, attr="content"):
                return tag.get(attr) if tag and tag.has_attr(attr) else (tag.text if tag else "")

            title_tag = soup.find("meta", property="og:title") or soup.find("title")
            desc_tag = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
            img_tag = soup.find("meta", property="og:image")
            vid_tag = soup.find("meta", property="og:video")

            title = safe_content(title_tag)
            description = safe_content(desc_tag)
            image = safe_content(img_tag)
            video = safe_content(vid_tag)

            # --- Fallback if no OG tags found ---
            if not (title or image or video):
                title = soup.title.string if soup.title else "Link Preview"
                first_img = soup.find("img")
                image = first_img["src"] if first_img and first_img.has_attr("src") else ""

            return JsonResponse({
                "link_preview": {
                    "url": url_param,
                    "title": title,
                    "description": description,
                    "image": image,
                    "video": video
                }
            })

        except Exception as e:
            # fallback for broken URLs
            return JsonResponse({
                "link_preview": {
                    "url": url_param,
                    "title": "",
                    "description": "",
                    "image": "",
                    "video": ""
                }
            })

    # --- CASE 2: Session-shared file ---
    file_name = request.session.pop("shared_file_name", None)
    file_content = request.session.pop("shared_file_content", None)
    shared_file = None

    if file_name and file_content:
        if not isinstance(file_content, str):
            file_content = base64.b64encode(file_content).decode("utf-8")
        shared_file = {"file": file_name, "content": file_content}

    prefill_text = request.session.pop("prefill_text", None)
    link_preview = None
    if prefill_text:
        link_preview = {"text": prefill_text}
        if prefill_text.startswith("http"):
            link_preview["url"] = prefill_text

    return JsonResponse({
        "shared_file": shared_file or {"file": None, "content": None},
        "link_preview": link_preview or None
    })





#_______________________________________________________________
## SHARING FUNCTION - DROP-IN READY

#_______________________________________________________________
from urllib.parse import quote

'''
def share_media(request, media_id):
    """
    Generate shareable link and sharing options for media
    
    ✅ MODIFIED: Points to explore_detail instead of separate public view
    No authentication required - anyone with link can access
    Works with existing Media model - NO migrations needed
    
    Returns:
    - Web Share API support detection
    - Platform-specific share links (WhatsApp, Facebook, Twitter, etc.)
    - Shareable URL (points to explore_detail)
    - QR code generation option
    """
    from service_auth.user_profile.models import Media
    from django.urls import reverse
    
    # Get media (works for both public and private based on your existing logic)
    media = get_object_or_404(Media, id=media_id)
    
    #  Build absolute URL for sharing - points to explore_detail
    share_url = request.build_absolute_uri(
        reverse('user_profile:explore_detail', kwargs={'media_id': media.id})
    )
    
    # Media details for sharing
    title = f"{media.user.username}'s post on Socyfie"
    description = media.description[:200] if media.description else "Check out this post!"
    
    # Get media file URL (absolute)
    if media.file:
        media_url = request.build_absolute_uri(media.file.url)
    else:
        media_url = None
    
    # Platform-specific share URLs
    share_links = {
        'whatsapp': f"https://wa.me/?text={quote(title + ' ' + share_url)}",
        'facebook': f"https://www.facebook.com/sharer/sharer.php?u={quote(share_url)}",
        'twitter': f"https://twitter.com/intent/tweet?url={quote(share_url)}&text={quote(title)}",
        'linkedin': f"https://www.linkedin.com/sharing/share-offsite/?url={quote(share_url)}",
        'telegram': f"https://t.me/share/url?url={quote(share_url)}&text={quote(title)}",
        'reddit': f"https://reddit.com/submit?url={quote(share_url)}&title={quote(title)}",
        'pinterest': f"https://pinterest.com/pin/create/button/?url={quote(share_url)}&description={quote(description)}&media={quote(media_url) if media_url else ''}",
        'email': f"mailto:?subject={quote(title)}&body={quote(description + ' ' + share_url)}",
    }
    
    # Check if request is AJAX (for modal popup)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if is_ajax:
        return JsonResponse({
            'success': True,
            'share_url': share_url,
            'share_links': share_links,
            'title': title,
            'description': description,
            'media_url': media_url,
            #'media_type': 'video' if media.is_video else 'image'
            'media_type': 'video' if media.media_type == 'video' else 'image'

        })
    
    # For non-AJAX requests, redirect to explore_detail
    from django.shortcuts import redirect
    return redirect('user_profile:explore_detail', media_id=media_id)
''' 
 
def generate_qr_code(request, media_id):
    """
    Generate QR code for media sharing
    
     MODIFIED: QR code points to explore_detail
    
    Optional - requires qrcode library
    Install: pip install qrcode[pil] --break-system-packages
    """
    try:
        import qrcode
        from io import BytesIO
        from django.http import HttpResponse
        from django.urls import reverse
        
        #  Build share URL pointing to explore_detail
        share_url = request.build_absolute_uri(
            reverse('user_profile:explore_detail', kwargs={'media_id': media_id})
        )
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(share_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to bytes
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        # Return image
        response = HttpResponse(buffer, content_type='image/png')
        response['Content-Disposition'] = f'inline; filename="qr_code_{media_id}.png"'
        return response
        
    except ImportError:
        return JsonResponse({
            'error': 'QR code library not installed. Run: pip install qrcode[pil] --break-system-packages'
        }, status=500)
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
 
 
@login_required
def download_media(request, media_id):
    """
    Download media file
    
    Respects privacy rules from your explore_detail function
    """
    from service_auth.user_profile.models import Media
    from service_auth.notion.models import Follow, Buddy
    
    media = get_object_or_404(Media, id=media_id)
    
    # Check permissions (same privacy logic as explore_detail)
    can_download = False
    user_id = request.user.id
    
    if media.user == request.user:
        can_download = True
    elif not media.is_private and not media.user.profile.is_private:
        can_download = True
    elif media.user.profile.is_private:
        # Check if following
        if Follow.objects.filter(follower=request.user, following=media.user).exists():
            if not media.is_private:
                can_download = True
    
    if media.is_private and not can_download:
        # Check if in buddy list
        if Buddy.objects.filter(user=media.user, buddy=request.user).exists():
            can_download = True
    
    if not can_download:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Serve file
    if media.file:
        response = FileResponse(media.file.open('rb'))
        filename = os.path.basename(media.file.name)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return JsonResponse({'error': 'No file available'}, status=404)



def share_media(request, media_id):
    """
    Generate shareable link and sharing options for media
    
    No authentication required - anyone with link can access
    Works with existing Media model - NO migrations needed
    
    Returns:
    - Web Share API support detection
    - Platform-specific share links (WhatsApp, Facebook, Twitter, etc.)
    - Shareable URL
    - QR code generation option
    """
    from service_auth.user_profile.models import Media
    
    # Get media (works for both public and private based on your existing logic)
    media = get_object_or_404(Media, id=media_id)
    
    # Build absolute URL for sharing
    #share_url = request.build_absolute_uri(f'/media/{media.id}/')
    share_url = request.build_absolute_uri(f'/explore_detail/{media.id}/')

    # Media details for sharing
    title = f"{media.user.username}'s post on Socyfie"
    description = media.description[:200] if media.description else "Check out this post!"
    
    # Get media file URL (absolute)
    if media.file:
        media_url = request.build_absolute_uri(media.file.url)
    else:
        media_url = None
    
    # Platform-specific share URLs
    share_links = {
        'whatsapp': f"https://wa.me/?text={quote(title + ' ' + share_url)}",
        'facebook': f"https://www.facebook.com/sharer/sharer.php?u={quote(share_url)}",
        'twitter': f"https://twitter.com/intent/tweet?url={quote(share_url)}&text={quote(title)}",
        'linkedin': f"https://www.linkedin.com/sharing/share-offsite/?url={quote(share_url)}",
        'telegram': f"https://t.me/share/url?url={quote(share_url)}&text={quote(title)}",
        'reddit': f"https://reddit.com/submit?url={quote(share_url)}&title={quote(title)}",
        'pinterest': f"https://pinterest.com/pin/create/button/?url={quote(share_url)}&description={quote(description)}&media={quote(media_url) if media_url else ''}",
        'email': f"mailto:?subject={quote(title)}&body={quote(description + ' ' + share_url)}",
    }
    
    # Check if request is AJAX (for modal popup)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if is_ajax:
        return JsonResponse({
            'success': True,
            'share_url': share_url,
            'share_links': share_links,
            'title': title,
            'description': description,
            'media_url': media_url,
            #'media_type': 'video' if media.is_video else 'image'
            'media_type': 'video' if media.media_type == 'video' else 'image'
            #'media_type': media.media_type or 'image'
        })
    
    # Regular page view
    context = {
        'media': media,
        'share_url': share_url,
        'share_links': share_links,
        'title': title,
        'description': description,
        'media_url': media_url,
    }
    
    #return render(request, 'share_media.html', context)
    #return redirect('user_profile:explore_detail', media_id=media_id)
    return redirect('user_profile:explore_detail', context)

 
@cache_control(public=True, max_age=3600)
def media_detail_public(request, media_id):
    """
    Public media detail page for shared links
    
    This is where shared links point to
    Includes Open Graph meta tags for rich previews
    """
    from service_auth.user_profile.models import Media
    
    media = get_object_or_404(Media, id=media_id)
    
    # Check privacy
    can_view = False
    
    if not media.is_private and not media.user.profile.is_private:
        # Public media and public profile
        can_view = True
    elif request.user.is_authenticated:
        # Check if user can view based on privacy rules
        if media.user == request.user:
            can_view = True  # Owner can always view
        elif media.user.profile.is_private:
            # Check if following
            from service_auth.notion.models import Follow
            is_following = Follow.objects.filter(
                follower=request.user,
                following=media.user
            ).exists()
            if is_following and not media.is_private:
                can_view = True
        
        if media.is_private and not can_view:
            # Check if in buddy list
            from service_auth.notion.models import Buddy
            is_buddy = Buddy.objects.filter(
                user=media.user,
                buddy=request.user
            ).exists()
            if is_buddy:
                can_view = True
    
    if not can_view:
        return render(request, 'media_private.html', {
            'message': 'This content is private'
        })
    
    # Build share URL
    share_url = request.build_absolute_uri(f'/media/{media.id}/')
    #share_url = request.build_absolute_uri(f'/explore_detail/{media.id}/')
 
    context = {
        'media': media,
        'share_url': share_url,
        'og_title': f"{media.user.username}'s post",
        'og_description': media.description[:200] if media.description else 'Check out this post!',
        'og_image': request.build_absolute_uri(media.file.url) if media.file else None,
    }
    
    #return render(request, 'media_detail_public.html', context)
    return redirect('user_profile:explore_detail', media_id=media_id)

 
''' 
def generate_qr_code(request, media_id):
    """
    Generate QR code for media sharing
    
    Optional - requires qrcode library
    Install: pip install qrcode[pil] --break-system-packages
    """
    try:
        import qrcode
        from io import BytesIO
        from django.http import HttpResponse
        
        # Build share URL
        share_url = request.build_absolute_uri(f'/media/{media_id}/')
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(share_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to bytes
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        # Return image
        response = HttpResponse(buffer, content_type='image/png')
        response['Content-Disposition'] = f'inline; filename="qr_code_{media_id}.png"'
        return response
        
    except ImportError:
        return JsonResponse({
            'error': 'QR code library not installed. Run: pip install qrcode[pil] --break-system-packages'
        }, status=500)
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
 
 
@login_required
def download_media(request, media_id):
    """
    Download media file
    
    Respects privacy rules
    """
    from service_auth.user_profile.models import Media
    from django.http import FileResponse
    import os
    
    media = get_object_or_404(Media, id=media_id)
    
    # Check permissions (same privacy logic as media_detail_public)
    can_download = False
    
    if media.user == request.user:
        can_download = True
    elif not media.is_private and not media.user.profile.is_private:
        can_download = True
    elif media.user.profile.is_private:
        from service_auth.notion.models import Follow
        if Follow.objects.filter(follower=request.user, following=media.user).exists():
            if not media.is_private:
                can_download = True
    
    if media.is_private and not can_download:
        from service_auth.notion.models import Buddy
        if Buddy.objects.filter(user=media.user, buddy=request.user).exists():
            can_download = True
    
    if not can_download:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Serve file
    if media.file:
        response = FileResponse(media.file.open('rb'))
        filename = os.path.basename(media.file.name)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return JsonResponse({'error': 'No file available'}, status=404)
'''
#_______________________________________________________________
## SHARING FUNCTION - DROP-IN READY

#_______________________________________________________________
