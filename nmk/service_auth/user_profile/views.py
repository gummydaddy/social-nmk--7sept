
import os
import json
import math
import random

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
from .forms import MediaForm, ProfileForm, CommentForm, AudioForm, CategorySelectionForm
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
#from .utils import normalize_media_url
import re
from django.db.models import F, Count, Q, Exists, OuterRef
from django.http import JsonResponse
from django.core.cache import cache
# from async_views import async_views

from .tasks import process_media_upload, process_profile_images
import base64
from bs4 import BeautifulSoup

from django.views.decorators.cache import cache_page, cache_control
from django.utils.decorators import method_decorator
import asyncio


import random
from collections import deque
from django.template.loader import render_to_string
from django.utils.html import escape, mark_safe
from django.urls import reverse
from random import shuffle
from django.utils.http import urlencode
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_headers
from django.core.files.uploadedfile import InMemoryUploadedFile
from datetime import datetime
from django.utils.timezone import now

from django_redis import get_redis_connection

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
SEARCH_HASHTAG_WEIGHT = 14

FOLLOWED_USER_MEDIA_WEIGHT = 30
FOLLOWED_USER_DESCRIPTION_WEIGHT = 8

ACTIVE_USER_WEIGHT = 12
HIGH_ENGAGEMENT_WEIGHT = 13

HIGH_FOLLOWER_THRESHOLD = 100_000
HIGH_INFLUENCER_BOOST = 15

CATEGORY_ENGAGEMENT_WEIGHT = 17
FRESHNESS_WEIGHT = 25
DIVERSITY_DECAY_RATE = 0.1
MAX_VIEWED_MEDIA_CACHE = 300
FALLBACK_MEDIA_COUNT = 24
#for cacshing media in explore_detail for 20 min delay 
COOLDOWN_MINUTES = 20
DESCRIPTION_PRIORITY_UNIT = 4   # points per overlapping word (kept modest)


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
    trending_key = f"trending_score:{media.id}"
    trending_score = cache.get(trending_key)

    if trending_score is not None:
        score += trending_score * 0.4  # Weight trending with 40% influence
    else:
        # Graceful fallback (no trending data yet)
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
@cache_page(60 * 1)
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
        return render(request, 'upload.html', {'form': form})




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
#@cache_page(60 * 3)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
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




@login_required
@cache_page(60 * 4)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def explore(request):
    user = request.user

    # Reset session and preference state
    if request.GET.get('reset') == '1':
        request.session.pop('explore_state', None)
        pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        pref.viewed_media = []
        pref.save()
        cache.delete(f'user_{user.id}_explore_served_ids')
        return redirect('user_profile:explore')

    # --- User preferences (only what’s actually used) ---
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

    # --- Blocked users ---
    blocked_me = list(BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True))
    i_blocked = list(BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True))

    # --- Served IDs from cache ---
    served_cache_key = f'user_{user.id}_explore_served_ids'
    already_served_ids = set(cache.get(served_cache_key, []))

    # --- Base Query ---
    base_qs = Media.objects.exclude(
        user__in=blocked_me
    ).exclude(
        user__in=i_blocked
    ).exclude(
        id__in=already_served_ids
    ).exclude(
        id__in=not_int_media_ids
    ).exclude(
        # Exclude media that is private and user not buddy
        Q(is_private=True) & ~Q(user__buddy_list__buddy=user)
    ).exclude(
        # Exclude media from private profiles unless buddy/follower/self
        Q(user__profile__is_private=True) &
        ~Q(user__buddy_list__buddy=user) &
        ~Q(user__follower_set__follower=user) &
        ~Q(user=user)
    ).order_by('-created_at')

    # --- Apply filters ---
    if hashtag_filter:
        base_qs = base_qs.filter(hashtags__name__icontains=hashtag_filter)
    if q_filter:
        base_qs = base_qs.filter(
            Q(description__icontains=q_filter) | Q(hashtags__name__icontains=q_filter)
        ).distinct()

    # --- Limit candidates ---
    TOP_CANDIDATES = 300
    media_ids = list(base_qs.values_list('id', flat=True)[:TOP_CANDIDATES])

    # --- Fetch media with only necessary fields, preserve order ---
    media_objs = Media.objects.filter(id__in=media_ids) \
        .select_related('user', 'user__profile') \
        .prefetch_related('hashtags', 'likes') \
        .only('id', 'user_id', 'created_at', 'description', 'file', 'thumbnail', 'is_private')

    media_map = {m.id: m for m in media_objs}
    media_list = [media_map[mid] for mid in media_ids if mid in media_map]

    # --- Scoring ---
    now = timezone.now()
    SCORING_NOISE = 3.0

    def score(media):
        base_score = calculate_media_score(
            media,
            liked_ht,
            not_int_ht,
            viewed_ht,
            search_ht,
            liked_cats,
        )
        age_hours = (now - media.created_at).total_seconds() / 3600
        base_score += max(FRESHNESS_WEIGHT - (age_hours * DIVERSITY_DECAY_RATE), 0)
        if media.user_id == user.id:
            base_score -= 100
        return base_score

    def noisy_score(media):
        return score(media) + random.uniform(-SCORING_NOISE, SCORING_NOISE)

    new_media = [m for m in media_list if m.id not in viewed_media_ids]
    old_media = [m for m in media_list if m.id in viewed_media_ids]

    scored_new = sorted(new_media, key=noisy_score, reverse=True)
    scored_old = sorted(old_media, key=noisy_score, reverse=True)
    sorted_media = scored_new + scored_old

    # --- Fallback ---
    if len(sorted_media) < 12:
        fallback = Media.objects.exclude(
            id__in=not_int_media_ids.union({m.id for m in sorted_media})
        ).annotate(
            likes_count=Count('likes')
        ).order_by('-likes_count', '-created_at')[:FALLBACK_MEDIA_COUNT]
        sorted_media += list(fallback)

    # --- Pagination ---
    paginator = Paginator(sorted_media, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # --- Update served IDs cache ---
    served_this_page = [media.id for media in page_obj]
    updated_served_ids = list(already_served_ids.union(served_this_page))
    cache.set(served_cache_key, updated_served_ids, timeout=60 * 30)

    # --- AJAX ---
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
            'has_next': page_obj.has_next(),  # ✅ fixed
            'current_page': page_obj.number,
        }, headers={'Cache-Control': 'public, max-age=120, s-maxage=120'})

    # --- Initial render ---
    return render(request, 'explore.html', {
        'page_obj': page_obj,
        'hashtag_filter': hashtag_filter,
        'q_filter': q_filter,
    })

@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
@login_required
def search_uploads(request):
    query = request.GET.get('q', '').strip()
    hashtag_filter = request.GET.get('hashtag', '').strip()

    # Fetch user preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    viewed_media = user_hashtag_pref.viewed_media
    liked_categories = user_hashtag_pref.liked_categories

    # Add search query to preferences
    if query:
        user_hashtag_pref.add_search_hashtag(query)

    # Exclude blocked users
    blocked_users = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    blocked_by_users = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)

    # Base queryset with eager loading
    media_objects = (
        Media.objects.filter(is_private=False, user__profile__is_private=False)
        .exclude(user__in=blocked_users)
        .exclude(user__in=blocked_by_users)
        .select_related("user", "user__profile")
        .prefetch_related("hashtags", "likes")
        .order_by("-created_at")
    )

    # Apply search filters
    if query:
        media_objects = media_objects.filter(
            Q(description__icontains=query) |
            Q(hashtags__name__icontains=query) |
            Q(user__username__icontains=query)
        )

    if hashtag_filter:
        media_objects = media_objects.filter(hashtags__name__icontains=hashtag_filter)

    # Shuffle for randomness
    media_list = list(media_objects.distinct())
    random.shuffle(media_list)

    # Calculate scores
    media_scores = [
        (media, calculate_media_score(
            media,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags,
            liked_categories
        ))
        for media in media_list
    ]

    sorted_media = [m[0] for m in sorted(media_scores, key=lambda x: x[1], reverse=True)]

    # Pagination
    paginator = Paginator(sorted_media, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Update viewed media
    new_viewed = set(viewed_media)
    for media in page_obj:
        if media.id not in new_viewed:
            new_viewed.add(media.id)
    user_hashtag_pref.viewed_media = list(new_viewed)
    user_hashtag_pref.save(update_fields=["viewed_media"])

    # AJAX response
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        media_list = [
            {
                "id": m.id,
                "file_url": m.file.url,
                "is_video": m.file.url.lower().endswith(".mp4"),
                "user_username": m.user.username,
                "description": m.description,
            }
            for m in page_obj
        ]
        return JsonResponse({"media": media_list})

    return render(request, "explore.html", {
        "page_obj": page_obj,
        "query": query,
        "hashtag_filter": hashtag_filter,
    })



@cache_page(60 * 5)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def explore_detail(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user

    # Serve preview for bots/crawlers (no login redirect)
    if is_crawler(request):
        description = make_usernames_clickable(media.description or "")
        return render(request, 'meta_preview.html', {
            'media': media,
            'description': description,
            'title': f"{user.username} on Socyfie",
            'image_url': media.file.url,
            'page_url': request.build_absolute_uri(),
        })

    user_id = getattr(request.user, "pk", None)  #  safe for anonymous

    # Block checks
    is_blocked_by_media_owner = BlockedUser.objects.filter(
        blocker=user, blocked_id=user_id
    ).exists() if user_id else False

    has_blocked_media_owner = BlockedUser.objects.filter(
        blocker_id=user_id, blocked=user
    ).exists() if user_id else False

    if is_blocked_by_media_owner:
        return render(request, 'user_not_found.html')

    # Following / buddy logic
    is_following = Follow.objects.filter(
        follower_id=user_id, following=user
    ).exists() if user_id else False

    is_buddy = Buddy.objects.filter(
        user=user, buddy_id=user_id
    ).exists() if user_id else False

    #  Restrict private content only
    if (media.is_private or user.profile.is_private):
        if not user_id or (not is_buddy and not is_following and request.user != user):
            return render(request, 'private_upload.html')

    # Preferences (only viewed_media + viewed_hashtags)
    if user_id:
        user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user_id=user_id)

        # Track viewed media
        if media.id not in user_hashtag_pref.viewed_media:
            viewed_media = user_hashtag_pref.viewed_media
            viewed_media.append(media.id)
            user_hashtag_pref.viewed_media = viewed_media[-MAX_VIEWED_MEDIA_CACHE:]
            user_hashtag_pref.save(update_fields=["viewed_media"])

        # Track viewed hashtags
        description_hashtags = re.findall(r'#(\w+)', media.description or "")
        user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    # Related media logic
    main_description_words = set(re.findall(r'\w+', (media.description or "").lower()))
    cache_key = f"user_{user_id or 'guest'}_related_viewed_{media_id}"
    related_already_sent_ids = set(cache.get(cache_key, []))

    related_qs = (
        Media.objects
        .select_related('user', 'user__profile')
        .prefetch_related('hashtags', 'likes')
        .exclude(id=media_id)
        .exclude(id__in=related_already_sent_ids)
    )

    #  Do not suggest private media / private profile media
    related_qs = related_qs.exclude(
        Q(is_private=True) |
        Q(user__profile__is_private=True)
    )

    #  Light Scoring Logic (Category + Freshness + Description overlap only)
    media_scores = []
    now_ts = now()
    for m in related_qs:
        score = 0
        # Category relevance
        if getattr(m, 'category', None) and getattr(media, 'category', None) and m.category == media.category:
            score += CATEGORY_ENGAGEMENT_WEIGHT

            # Freshness inside category
            if getattr(m, 'created_at', None):
                days_old = (now_ts - m.created_at).days if m.created_at else 9999
                score += max(0, FRESHNESS_WEIGHT - days_old)

            # Description overlap inside category
            desc = (m.description or "").lower()
            if desc:
                overlap = main_description_words & set(re.findall(r'\w+', desc))
                if overlap:
                    score += 6 * len(overlap)

        media_scores.append((m, score))

    #  Sort
    media_scores.sort(key=lambda x: (x[1], getattr(x[0], 'created_at', now_ts)), reverse=True)
    related_sorted = [m for m, _ in media_scores]

    # Pagination
    paginator = Paginator(related_sorted, 8)
    page = request.GET.get('page', 1)
    try:
        related_media_paginated = paginator.page(page)
    except PageNotAnInteger:
        related_media_paginated = paginator.page(1)
    except EmptyPage:
        related_media_paginated = paginator.page(paginator.num_pages)

    page_related_ids = [m.id for m in related_media_paginated]
    cache.set(cache_key, list(related_already_sent_ids.union(page_related_ids)), timeout=60 * 30)

    # Engagement / view count
    if user_id:
        if not Engagement.objects.filter(user_id=user_id, media=media, engagement_type='view').exists():
            Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
            Engagement.objects.create(media=media, user_id=user_id, engagement_type='view')
    else:
        Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)

    description_html = make_usernames_clickable(media.description or "")

    # AJAX infinite scroll
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        related_media_list = [
            {
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.lower().endswith('.mp4'),
                'thumbnail_url': (m.thumbnail.url if getattr(m, 'thumbnail', None) else None),
                'likes_count': m.likes.count(),
                'user_username': m.user.username,
                'user_id': m.user_id,
            }
            for m in related_media_paginated
        ]
        return JsonResponse({
            'related_media': related_media_list,
            'has_next': related_media_paginated.has_next()
        })

    # Normal render
    return render(request, 'explore_detail.html', {
        'media': media,
        'related_media': related_media_paginated,
        'description': description_html,
        'is_buddy': is_buddy,
        'is_following': is_following,
        'has_blocked_media_owner': has_blocked_media_owner,
        'is_blocked_by_media_owner': is_blocked_by_media_owner,
    })



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
'''
from .utils import (
    GLOBAL_EXPLORE_CACHE_KEY,
    GLOBAL_EXPLORE_CACHE_TIMEOUT,
    GLOBAL_EXPLORE_CAP,
    build_and_cache_global_explore,
    get_global_explore_ids,
    get_media_qs_from_cached_ids,
    _serialize_media_for_cache,
)

@cache_page(60 * 3)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def following_media(request):
    user = request.user

    # -------------------------
    # Anonymous users
    # -------------------------
    if not user.is_authenticated:
        explore_media = Media.objects.filter(
            is_private=False,
            user__profile__is_private=False
        ).select_related('user', 'user__profile').prefetch_related('hashtags', 'likes').annotate(
            likes_count=Count('likes')
        ).order_by('-created_at')

        for media in explore_media:
            media.description = make_usernames_clickable(media.description)

        paginator = Paginator(explore_media, 6)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            media_list = []
            for m in page_obj:
                try:
                    profile_picture_url = m.user.profile.profile_picture.url
                except Exception:
                    profile_picture_url = '/static/images/logo.png'

                media_list.append({
                    'id': m.id,
                    'file_url': m.file.url,
                    'is_video': m.file.url.endswith('.mp4'),
                    'user_username': m.user.username,
                    'description': m.description,
                    'likes_count': m.likes.count(),
                    'is_liked': False,
                    'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
                    'view_count': m.view_count,
                    'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': m.id}),
                    'profile_url': reverse('user_profile:profile', kwargs={'user_id': m.user.id}),
                    'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
                    'profile_picture_url': profile_picture_url,
                })

            return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

        return render(request, 'following_media.html', {'page_obj': page_obj, 'following_ids': set()})

    # -------------------------
    # Authenticated users
    # -------------------------
    following_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    users_blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)
    followed_users = AuthUser.objects.filter(
        follower_set__follower=user
    ).exclude(id__in=users_blocked_me).exclude(id__in=users_i_blocked)
    buddy_list = Buddy.objects.filter(user=user).values_list('buddy', flat=True)

    # -----------------------------
    # User preferences
    # -----------------------------
    user_pref_cache_key = f'user_pref_{user.id}'
    prefs = cache.get(user_pref_cache_key)
    if not prefs:
        user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        prefs = {
            "liked_hashtags": user_hashtag_pref.liked_hashtags,
            "not_interested_hashtags": user_hashtag_pref.not_interested_hashtags,
            "viewed_hashtags": user_hashtag_pref.viewed_hashtags,
            "search_hashtags": user_hashtag_pref.search_hashtags,
            "liked_categories": user_hashtag_pref.liked_categories,
        }
        cache.set(user_pref_cache_key, prefs, 300)

    liked_hashtags = prefs["liked_hashtags"]
    not_interested_hashtags = prefs["not_interested_hashtags"]
    viewed_hashtags = prefs["viewed_hashtags"]
    search_hashtags = prefs["search_hashtags"]
    liked_categories = prefs["liked_categories"]

    # -----------------------------
    # Served media cache
    # -----------------------------
    served_media_cache_key = f'user_{user.id}_served_media_ids'
    already_sent_ids = set(cache.get(served_media_cache_key, []))

    # -----------------------------
    # Recent likes (personalization)
    # -----------------------------
    recent_liked_media = Media.objects.filter(
        engagement__user=user,
        engagement__engagement_type='like'
    ).order_by('-created_at')[:30]

    recent_interest_hashtags = set()
    recent_interest_categories = set()
    recent_interest_words = set()
    for media in recent_liked_media:
        recent_interest_hashtags.update(h.name.lower() for h in media.hashtags.all())
        if getattr(media, "category", None):
            recent_interest_categories.add(media.category.lower())
        desc = (media.description or "").lower()
        for word in desc.split():
            if len(word) > 3 and word.isalnum():
                recent_interest_words.add(word)

    # -----------------------------
    # Media queryset
    # -----------------------------
    media_from_followed_users = Media.objects.filter(
        Q(user__in=followed_users) | Q(user__in=buddy_list)
    ).exclude(id__in=already_sent_ids).select_related(
        'user', 'user__profile'
    ).prefetch_related('hashtags', 'likes').annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at').exclude(
        Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
    )

    explore_media = Media.objects.exclude(
        user__in=users_blocked_me
    ).exclude(
        user__in=users_i_blocked
    ).exclude(
        id__in=already_sent_ids
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related('hashtags', 'likes').annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at')

    combined_media = list(media_from_followed_users) + list(explore_media)

    # -----------------------------
    # Followed users preferences
    # -----------------------------
    followed_users_ids = followed_users.values_list('id', flat=True)
    followed_users_prefs = UserHashtagPreference.objects.filter(user_id__in=followed_users_ids)

    followed_users_media_ids = set()
    followed_descriptions_keywords = set()
    for pref in followed_users_prefs:
        followed_users_media_ids.update(pref.viewed_media or [])
        followed_descriptions_keywords.update(pref.search_hashtags or [])
        followed_descriptions_keywords.update(pref.liked_hashtags or [])

    liked_media_by_followed = Engagement.objects.filter(
        user_id__in=followed_users_ids,
        engagement_type='like'
    ).values_list('media_id', flat=True)
    followed_users_media_ids.update(liked_media_by_followed)

    # -----------------------------
    # Batch score caching in Redis
    # -----------------------------
    now = timezone.now()
    user_score_cache_key = f'user_{user.id}_media_scores'
    media_scores_dict = cache.get(user_score_cache_key, {})

    # Prefetch trending scores in bulk to reduce Redis round-trips
    trending_keys = [f"trending_score:{m.id}" for m in combined_media]
    trending_values = cache.get_many(trending_keys)

    media_scores = []
    for m in combined_media:
        if str(m.id) in media_scores_dict:
            score = media_scores_dict[str(m.id)]
        else:
            desc_lower = (m.description or "").lower()
            matched_description = any(tag.lower() in desc_lower for tag in followed_descriptions_keywords)

            score = calculate_media_score(
                m,
                liked_hashtags,
                not_interested_hashtags,
                viewed_hashtags,
                search_hashtags,
                liked_categories,
                followed_users_media_ids=followed_users_media_ids,
                followed_users_descriptions_matches=matched_description,
                user=user
            )
            # Integrate cached trending score (if available)
            trending_score = trending_values.get(f"trending_score:{m.id}", 0)
            score += trending_score * 0.4  # use same scaling factor as calculate_media_score()

            # Interest-based bonuses
            if any(tag in desc_lower for tag in recent_interest_hashtags):
                score += 5
            if getattr(m, "category", None) and m.category.lower() in recent_interest_categories:
                score += 3
            if any(word in desc_lower for word in recent_interest_words):
                score += 2

            # Recency boost
            age_seconds = (now - m.created_at).total_seconds()
            recency_boost = max(0, (86400 * 2 - age_seconds) / 86400)
            score += recency_boost

            # Save to batch dict
            media_scores_dict[str(m.id)] = score

        media_scores.append((m, score))

    # Cache entire batch for 10 minutes
    cache.set(user_score_cache_key, media_scores_dict, timeout=600)

    # -----------------------------
    # Sort & privacy filter
    # -----------------------------
    sorted_media = [m for m, _ in sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)]
    sorted_media = [
        m for m in sorted_media
        if not (m.is_private and not Buddy.objects.filter(user=m.user, buddy=user).exists() and user != m.user)
        and not (m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists())
    ]

    random.shuffle(sorted_media)
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    paginator = Paginator(sorted_media, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update served cache
    sent_ids = [m.id for m in page_obj]
    cache.set(served_media_cache_key, list(already_sent_ids.union(sent_ids)), timeout=600)

    # -----------------------------
    # AJAX response
    # -----------------------------
    media_list = []
    for m in page_obj:
        try:
            profile_picture_url = m.user.profile.profile_picture.url
        except Exception:
            profile_picture_url = '/static/images/logo.png'

        show_follow = False
        if not request.user.is_authenticated:
            show_follow = True
        elif request.user != m.user and m.user.id not in following_ids:
            show_follow = True

        media_list.append({
            'id': m.id,
            'file_url': m.file.url,
            'is_video': m.file.url.endswith('.mp4'),
            'user_username': m.user.username,
            'description': m.description,
            'likes_count': m.likes.count(),
            'is_liked': request.user in m.likes.all(),
            'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
            'view_count': m.view_count,
            'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': m.id}),
            'profile_url': reverse('user_profile:profile', kwargs={'user_id': m.user.id}),
            'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
            'profile_picture_url': profile_picture_url,
            'show_follow': show_follow,
            'follow_url': reverse("user_profile:follow_user", kwargs={"user_id": m.user.id}) if show_follow else None,
        })

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

    return render(request, 'following_media.html', {'page_obj': page_obj, 'following_ids': following_ids})
'''

#with global cache setup
from .utils import (
    GLOBAL_EXPLORE_CACHE_KEY,
    GLOBAL_EXPLORE_CACHE_TIMEOUT,
    GLOBAL_EXPLORE_CAP,
    build_and_cache_global_explore,
    get_global_explore_ids,
    get_media_qs_from_cached_ids,
    _serialize_media_for_cache,
)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
@cache_page(60 * 3)
def following_media(request):
    user = request.user

    # -------------------------
    # Anonymous users - simpler path
    # -------------------------
    if not user.is_authenticated:
        explore_media_qs = Media.objects.filter(
            is_private=False,
            user__profile__is_private=False
        ).select_related('user', 'user__profile').prefetch_related('hashtags', 'likes').annotate(
            likes_count=Count('likes')
        ).order_by('-created_at')

        # make usernames clickable safely (your function)
        for media in explore_media_qs:
            media.description = make_usernames_clickable(media.description)

        paginator = Paginator(explore_media_qs, 6)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            media_list = []
            for m in page_obj:
                # safe profile picture retrieval
                try:
                    profile_picture_url = m.user.profile.profile_picture.url
                except Exception:
                    profile_picture_url = '/static/images/logo.png'

                # safe reverse - guard against missing user.id
                profile_url = None
                try:
                    if getattr(m.user, 'id', None):
                        profile_url = reverse('user_profile:profile', kwargs={'user_id': m.user.id})
                except NoReverseMatch:
                    profile_url = None

                media_list.append({
                    'id': m.id,
                    'file_url': m.file.url,
                    'is_video': (m.media_type == 'video') or (m.file.name.lower().endswith('.mp4')),
                    'user_username': m.user.username,
                    'description': m.description,
                    'likes_count': m.likes.count(),
                    'is_liked': False,
                    'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
                    'view_count': m.view_count,
                    'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': m.id}),
                    'profile_url': profile_url,
                    'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
                    'profile_picture_url': profile_picture_url,
                })

            return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

        return render(request, 'following_media.html', {'page_obj': page_obj, 'following_ids': set()})

    # -------------------------
    # Authenticated users
    # -------------------------
    following_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    users_blocked_me = set(BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True))
    users_i_blocked = set(BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True))
    followed_users = AuthUser.objects.filter(
        follower_set__follower=user
    ).exclude(id__in=users_blocked_me).exclude(id__in=users_i_blocked)
    buddy_list = set(Buddy.objects.filter(user=user).values_list('buddy', flat=True))

    # -----------------------------
    # User preferences
    # -----------------------------
    user_pref_cache_key = f'user_pref_{user.id}'
    prefs = cache.get(user_pref_cache_key)
    if not prefs:
        user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        prefs = {
            "liked_hashtags": user_hashtag_pref.liked_hashtags,
            "not_interested_hashtags": user_hashtag_pref.not_interested_hashtags,
            "viewed_hashtags": user_hashtag_pref.viewed_hashtags,
            "search_hashtags": user_hashtag_pref.search_hashtags,
            "liked_categories": user_hashtag_pref.liked_categories,
        }
        cache.set(user_pref_cache_key, prefs, 300)

    liked_hashtags = prefs["liked_hashtags"]
    not_interested_hashtags = prefs["not_interested_hashtags"]
    viewed_hashtags = prefs["viewed_hashtags"]
    search_hashtags = prefs["search_hashtags"]
    liked_categories = prefs["liked_categories"]

    # -----------------------------
    # Served media cache (user-specific)
    # -----------------------------
    served_media_cache_key = f'user_{user.id}_served_media_ids'
    already_sent_ids = set(cache.get(served_media_cache_key, []))

    # -----------------------------
    # Recent likes (personalization)
    # -----------------------------
    recent_liked_media = Media.objects.filter(
        engagement__user=user,
        engagement__engagement_type='like'
    ).order_by('-created_at')[:30]

    recent_interest_hashtags = set()
    recent_interest_categories = set()
    recent_interest_words = set()
    for media in recent_liked_media:
        recent_interest_hashtags.update(h.name.lower() for h in media.hashtags.all())
        if getattr(media, "category", None):
            recent_interest_categories.add(media.category.lower())
        desc = (media.description or "").lower()
        for word in desc.split():
            if len(word) > 3 and word.isalnum():
                recent_interest_words.add(word)

    # -----------------------------
    # Media from followed users (dynamic)
    # -----------------------------
    # We keep followed-user feed dynamic because it is highly personalized.
    media_from_followed_users = Media.objects.filter(
        Q(user__in=followed_users) | Q(user__in=buddy_list)
    ).exclude(id__in=already_sent_ids).select_related(
        'user', 'user__profile'
    ).prefetch_related('hashtags', 'likes').annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at').exclude(
        Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
    )

    # -----------------------------
    # Use GLOBAL EXPLORE CACHE (Option A)
    # -----------------------------
    global_ids = get_global_explore_ids()
    if global_ids is None:
        # build cache if missing
        try:
            global_ids = build_and_cache_global_explore()
        except Exception:
            # fallback to direct DB query if something fails
            logger.exception("Global explore cache build failed; falling back to DB query")
            global_ids = list(
                Media.objects.exclude(user__in=users_blocked_me).exclude(user__in=users_i_blocked)
                .select_related('user', 'user__profile')
                .prefetch_related('hashtags', 'likes')
                .order_by('-created_at').values_list('id', flat=True)[:GLOBAL_EXPLORE_CAP]
            )

    # Use only IDs not already sent
    filtered_ids = [mid for mid in global_ids if mid not in already_sent_ids]
    # For safety, select at most GLOBAL_EXPLORE_CAP of remaining ids
    filtered_ids = filtered_ids[:GLOBAL_EXPLORE_CAP]

    # Fetch only the Media objects we will actually process (limit to reasonable number)
    # This hits DB but only for the slice we need (not the whole dataset).
    explore_media_qs = get_media_qs_from_cached_ids(filtered_ids, exclude_ids=already_sent_ids, limit=GLOBAL_EXPLORE_CAP)

    # -----------------------------
    # Combine feeds (followed first)
    # -----------------------------
    # Convert querysets to lists (so we can mix)
    combined_media = list(media_from_followed_users) + list(explore_media_qs)

    # -----------------------------
    # Followed users preferences (existing)
    # -----------------------------
    followed_users_ids = followed_users.values_list('id', flat=True)
    followed_users_prefs = UserHashtagPreference.objects.filter(user_id__in=followed_users_ids)

    followed_users_media_ids = set()
    followed_descriptions_keywords = set()
    for pref in followed_users_prefs:
        followed_users_media_ids.update(pref.viewed_media or [])
        followed_descriptions_keywords.update(pref.search_hashtags or [])
        followed_descriptions_keywords.update(pref.liked_hashtags or [])

    liked_media_by_followed = Engagement.objects.filter(
        user_id__in=followed_users_ids,
        engagement_type='like'
    ).values_list('media_id', flat=True)
    followed_users_media_ids.update(liked_media_by_followed)

    # -----------------------------
    # Batch score caching in Redis (user-specific)
    # -----------------------------
    now = timezone.now()
    user_score_cache_key = f'user_{user.id}_media_scores'
    media_scores_dict = cache.get(user_score_cache_key, {})

    # Prefetch trending scores in bulk to reduce Redis round-trips
    trending_keys = [f"trending_score:{m.id}" for m in combined_media]
    trending_values = cache.get_many(trending_keys)

    media_scores = []
    for m in combined_media:
        mid = str(m.id)
        if mid in media_scores_dict:
            score = media_scores_dict[mid]
        else:
            desc_lower = (m.description or "").lower()
            matched_description = any(tag.lower() in desc_lower for tag in followed_descriptions_keywords)

            try:
                score = calculate_media_score(
                    m,
                    liked_hashtags,
                    not_interested_hashtags,
                    viewed_hashtags,
                    search_hashtags,
                    liked_categories,
                    followed_users_media_ids=followed_users_media_ids,
                    followed_users_descriptions_matches=matched_description,
                    user=user
                )
            except Exception as e:
                logger.exception("calculate_media_score failed for media id %s: %s", m.id, e)
                # fallback to simple score
                score = (getattr(m, 'likes_count', 0) or m.likes.count()) + (m.view_count or 0) * 0.01

            # Integrate cached trending score (if available)
            trending_score = trending_values.get(f"trending_score:{m.id}", 0)
            try:
                score += trending_score * 0.4
            except Exception:
                score += 0

            # Interest-based bonuses
            try:
                if any(tag in desc_lower for tag in recent_interest_hashtags):
                    score += 5
                if getattr(m, "category", None) and m.category.lower() in recent_interest_categories:
                    score += 3
                if any(word in desc_lower for word in recent_interest_words):
                    score += 2
            except Exception:
                pass

            # Recency boost
            try:
                age_seconds = (now - m.created_at).total_seconds()
                recency_boost = max(0, (86400 * 2 - age_seconds) / 86400)
                score += recency_boost
            except Exception:
                pass

            # Save to batch dict
            media_scores_dict[mid] = score

        media_scores.append((m, score))

    # Cache entire batch for 10 minutes
    cache.set(user_score_cache_key, media_scores_dict, timeout=600)

    # -----------------------------
    # Sort & privacy filter
    # -----------------------------
    sorted_media = [m for m, _ in sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)]
    sorted_media = [
        m for m in sorted_media
        if not (m.is_private and not Buddy.objects.filter(user=m.user, buddy=user).exists() and user != m.user)
        and not (m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists())
    ]

    # Shuffle for randomness while keeping a sorted order baseline
    random.shuffle(sorted_media)

    # Ensure usernames clickable
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    paginator = Paginator(sorted_media, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update served cache (append newly sent ids)
    sent_ids = [m.id for m in page_obj]
    try:
        cache.set(served_media_cache_key, list(already_sent_ids.union(sent_ids)), timeout=600)
    except Exception:
        logger.exception("Failed to update served_media_cache_key for user %s", user.id)

    # -----------------------------
    # AJAX response building (safe URLs)
    # -----------------------------
    media_list = []
    for m in page_obj:
        # safe profile picture retrieval
        try:
            profile_picture_url = m.user.profile.profile_picture.url
        except Exception:
            profile_picture_url = '/static/images/logo.png'

        show_follow = False
        if not request.user.is_authenticated:
            show_follow = True
        elif request.user != m.user and m.user.id not in following_ids:
            show_follow = True

        # safe profile_url reverse
        profile_url = None
        try:
            if getattr(m.user, 'id', None):
                profile_url = reverse('user_profile:profile', kwargs={'user_id': m.user.id})
        except NoReverseMatch:
            profile_url = None

        media_list.append({
            'id': m.id,
            'file_url': m.file.url,
            'is_video': (m.media_type == 'video') or (m.file.name.lower().endswith('.mp4')),
            'user_username': m.user.username,
            'description': m.description,
            'likes_count': getattr(m, 'likes_count', m.likes.count()),
            'is_liked': request.user in m.likes.all(),
            'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
            'view_count': m.view_count,
            'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': m.id}),
            'profile_url': profile_url,
            'profile_picture_url': profile_picture_url,
            'show_follow': show_follow,
            'follow_url': reverse("user_profile:follow_user", kwargs={"user_id": m.user.id}) if show_follow and getattr(m.user, 'id', None) else None,
            'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
        })

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

    return render(request, 'following_media.html', {'page_obj': page_obj, 'following_ids': following_ids})


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


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def media_engagement(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    engagements = Engagement.objects.filter(media=media).exclude(user=media.user)

    # Count engagements by type
    engagement_summary = engagements.values('engagement_type').annotate(count=Count('id'))

    context = {
        'media': media,
        'engagement_summary': engagement_summary,
    }
    return render(request, 'media_engagement.html', context)

#new for specific description search 


@csrf_exempt
@require_POST
def log_interaction(request):
    try:
        if request.content_type != 'application/json':
            return JsonResponse({'error': 'Invalid content type'}, status=400)

        data = json.loads(request.body)
        media_id = data.get('media_id')
        interaction_type = data.get('interaction_type', 'view')  # Can be view, like, comment

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

        # Create the Interaction entry
        Interaction.objects.create(
            media=media,
            user=request.user,
            interaction_type=interaction_type
        )

        #  Optionally: Mirror the same interaction in Engagement model
        Engagement.objects.create(
            media=media,
            user=request.user,
            engagement_type=interaction_type
        )

        return JsonResponse({'success': True})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        print(f"Error in log_interaction: {e}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)



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
#to create likes
@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def like_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

    # Check if the user has already liked the media
    if request.user in media.likes.all():
        media.likes.remove(request.user)
        liked = False
    else:
        media.likes.add(request.user)
        liked = True
        user_hashtag_pref.add_liked_category(media.category)  # Track engagement with the media's category

        # Update the liked hashtags list based on the media description
        hashtags_in_description = re.findall(r'#(\w+)', media.description)
        for hashtag in hashtags_in_description:
            user_hashtag_pref.liked_hashtags = add_to_fifo_list(user_hashtag_pref.liked_hashtags, hashtag)

        user_hashtag_pref.save()

        # Create a clickable notification for the media owner
        if request.user != media.user:  # Avoid notifying the media owner if they like their own media
            Notification.objects.create(
                user=media.user,
                content=f'{request.user.username} liked your media: <a href="{reverse("user_profile:media_detail_view", args=[media.id])}">View Media</a>',
                type='like',
                related_user=request.user,
                related_media=media
            )

    # Handle AJAX requests to return like status and like count
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'like_count': media.likes.count()})

    # Redirect back to the referring page or to the media detail view
    return redirect(request.META.get('HTTP_REFERER', reverse('user_profile:media_detail_view', args=[media.id])))
'''


#@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def like_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = request.user

    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)

    # Check if the user has already liked the media
    if user in media.likes.all():
        media.likes.remove(user)
        liked = False
    else:
        media.likes.add(user)
        liked = True

        #  Check if user has a 'view' engagement entry for this media
        view_exists = Engagement.objects.filter(user=user, media=media, engagement_type='view').exists()

        #  If not viewed yet, increase the view count just like explore_detail
        if not view_exists:
            Media.objects.filter(pk=media.pk).update(view_count=F('view_count') + 1)
            Engagement.objects.create(media=media, user=user, engagement_type='view')

            # Also store the viewed media ID in the user's hashtag preferences (for caching logic)
            viewed_media = user_hashtag_pref.viewed_media
            if media.id not in viewed_media:
                viewed_media.append(media.id)
                user_hashtag_pref.viewed_media = viewed_media[-MAX_VIEWED_MEDIA_CACHE:]
                user_hashtag_pref.save(update_fields=["viewed_media"])

        #  Track engagement with the media's category
        user_hashtag_pref.add_liked_category(media.category)

        #  Update liked hashtags list based on the media description
        hashtags_in_description = re.findall(r'#(\w+)', media.description or "")
        for hashtag in hashtags_in_description:
            user_hashtag_pref.liked_hashtags = add_to_fifo_list(user_hashtag_pref.liked_hashtags, hashtag)
        user_hashtag_pref.save()

        #  Create a clickable notification for the media owner
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
        return JsonResponse({'liked': liked, 'like_count': media.likes.count(), 'view_count': media.view_count})

    #  Redirect if not AJAX
    return redirect(request.META.get('HTTP_REFERER', reverse('user_profile:media_detail_view', args=[media.id])))




@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def comment_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    
    if request.method == 'POST':
        content = request.POST.get('content', '')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        # Transform content to include clickable usernames and sanitize it
        content = make_usernames_clickable(escape(content))

        # Create the comment associated with the media
        comment = Comment.objects.create(user=request.user, media=media, content=content)

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
                    content=f'{request.user.username} mentioned you in a comment: <a href="{reverse("user_profile:media_detail_view", args=[media.id])}#{comment.id}">View Comment</a>',
                    type='mention',
                    related_user=request.user,
                    related_media=media,
                    comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        # Create a notification for the media owner
        if request.user != media.user:  # Avoid notifying the media owner if they are commenting on their own media
            Notification.objects.create(
                user=media.user,
                content=f'{request.user.username} commented on your media: <a href="{reverse("user_profile:media_detail_view", args=[media.id])}#{comment.id}">View Comment</a>',
                type='comment',
                related_user=request.user,
                related_media=media,
                comment=comment
            )

        # Redirect to the media detail view with the new comment's anchor (scroll to the comment)
        return redirect(f"{reverse('user_profile:media_detail_view', args=[media.id])}#{comment.id}")

    # If not POST, fallback to redirecting to the media detail page
    return redirect(reverse('user_profile:media_detail_view', args=[media.id]))



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



@cache_page(60 * 1)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def media_detail_view(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user  # The owner of the media
    user_id = getattr(request.user, "pk", None)  # ✅ safe for anonymous

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
@cache_page(60 * 30)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def profile_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(notifications, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'profile_notifications.html', {'page_obj': page_obj})



'''
@login_required
def edit_profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    profile, created = Profile.objects.get_or_create(user=profile_user)

    # Initialize forms
    profile_form = ProfileForm(instance=profile)
    username_form = UsernameUpdateForm(initial={'new_username': profile_user.username})
    category_form = CategorySelectionForm(instance=profile)  # Category selection form

    if request.method == 'POST':
        if 'save_changes' in request.POST:  # Handle profile updates
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)

            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully!')
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

    return render(request, 'edit_profile.html', {
        'form': profile_form,
        'username_form': username_form,
        'category_form': category_form,  # Include the category form
        'profile_user': profile_user
    })
'''

@login_required
@cache_page(60 * 30)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def edit_profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    profile, created = Profile.objects.get_or_create(user=profile_user)

    # Initialize forms
    profile_form = ProfileForm(instance=profile)
    username_form = UsernameUpdateForm(initial={'new_username': profile_user.username})
    category_form = CategorySelectionForm(instance=profile)  # Category selection form

    if request.method == 'POST':
        if 'save_changes' in request.POST:  # Handle profile updates
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)

            if profile_form.is_valid():
                saved_profile = profile_form.save()  # quick save
                # ✅ Launch Celery task asynchronously
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

    return render(request, 'edit_profile.html', {
        'form': profile_form,
        'username_form': username_form,
        'category_form': category_form,  # Include the category form
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
]

@login_required
@cache_page(60 * 30)
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
@cache_page(60 * 30)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def fetch_categories(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'categories': CATEGORY_CHOICES  # Return the choices as a list
        })
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
@cache_page(60 * 30)
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



@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def delete_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)

    # Check if the media being deleted is associated with the active story
    active_story = Story.objects.filter(media=media).first()

    if request.method == 'POST':
        # Delete the media file
        media.file.delete(save=False)
        media.delete()

        # If this media is the active story, delete the associated story
        if active_story:
            active_story.delete()

        return redirect('user_profile:profile', user_id=request.user.id)

    context = {'media': media}
    return render(request, 'user_profile/delete_media.html', context)


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


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def not_interested(request, media_id: int):
    """
    Adds media to user's not interested list and hashtags from media description 
    to the user's not interested hashtags list.

    Args:
    - request (HttpRequest)
    - media_id (int)

    Returns:
    - JsonResponse or HttpResponseRedirect
    """
    try:
        media = get_object_or_404(Media, id=media_id)
        user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

        # Add the media ID to the not interested media list
        user_hashtag_pref.add_not_interested_media(media_id)

        # Extract hashtags from the media description
        hashtags = re.findall(r'#(\w+)', media.description)

        # Add each hashtag to the user's not interested list
        for hashtag in hashtags:
            user_hashtag_pref.not_interested_hashtags = add_to_fifo_list(user_hashtag_pref.not_interested_hashtags, hashtag)

        # Save the updated user hashtag preference
        user_hashtag_pref.save()

        # Return a success response for AJAX requests
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': 'Media and hashtags added to not interested list'})

        # Redirect back to the referring page for regular requests
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    except Exception as e:
        # Log the error and return an error response
        return HttpResponse('Error occurred', status=500)



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


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def toggle_privacy(request):
    profile = request.user.profile
    profile.is_private = not profile.is_private
    profile.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_private': profile.is_private})
    
    return redirect('user_profile:profile', user_id=request.user.id)


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def toggle_media_privacy(request, media_id):
    media = get_object_or_404(Media, id=media_id, user=request.user)

    # Toggle the privacy status
    media.is_private = not media.is_private
    media.save()

    # Return the new privacy status as JSON
    return JsonResponse({'is_private': media.is_private})


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
@cache_page(60 * 30)
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
#for directly sharing without taking to the upload form 
'''
@csrf_exempt
@login_required
def share_upload(request):
    """
    Handles media shared directly to the PWA via share_target.
    Skips the upload form and directly saves media.
    """
    if request.method == "POST":
        file = request.FILES.get("file")
        text = request.POST.get("text", "")
        url = request.POST.get("url", "")
        description = text or url

        if not file:
            # Nothing shared → fallback to upload form
            return redirect("user_profile:upload_media")

        # Create media object (not processed yet)
        media = Media.objects.create(
            user=request.user,
            description=escape(description),
            media_type="image" if file.content_type.startswith("image/") else "video",
            is_processed=False,
        )

        # Save temp file for Celery
        ext = os.path.splitext(file.name)[1]
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
                for chunk in file.chunks():
                    temp.write(chunk)
                temp_file_path = temp.name
        except Exception as e:
            return JsonResponse({"status": "temp_file_error", "error": str(e)}, status=500)

        # Offload processing to Celery
        process_media_upload.delay(
            media.id,
            temp_file_path,
            file.name,
            media.media_type,
            None if media.media_type == "video" else request.POST.get("filter")
        )

        # Extract mentions + hashtags
        tagged_usernames = set(re.findall(r"@(\w+)", description or ""))
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

        # Redirect user to media detail page after upload
        #return redirect("user_profile:media_detail_view", media_id=media.id)
        return redirect("user_profile:following_media")

    # If GET or other method → show normal upload page
    return redirect("user_profile:upload_media")
'''


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


'''
def get_shared_file(request):
    """
    Return and clear shared file from the session for upload prefill,
    and also return link preview metadata if 'prefill_text' is a URL.
    """
    # --- Handle shared file ---
    file_name = request.session.pop('shared_file_name', None)
    file_content = request.session.pop('shared_file_content', None)
    shared_file = None

    if file_name and file_content:
        if not isinstance(file_content, str):
            file_content = base64.b64encode(file_content).decode('utf-8')
        shared_file = {'file': file_name, 'content': file_content}

    # --- Handle prefill text / URL ---
    prefill_text = request.session.pop('prefill_text', None)
    link_preview = None

    if prefill_text:
        # If it looks like a URL, attempt to fetch preview metadata
        if prefill_text.startswith("http"):
            try:
                resp = requests.get(prefill_text, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(resp.text, 'html.parser')

                title_tag = soup.find("meta", property="og:title") or soup.find("title")
                desc_tag = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                img_tag = soup.find("meta", property="og:image")

                title = title_tag.get("content") if title_tag and title_tag.has_attr("content") else (title_tag.text if title_tag else "")
                description = desc_tag.get("content") if desc_tag else ""
                image = img_tag.get("content") if img_tag else ""

                link_preview = {
                    "url": prefill_text,
                    "title": title,
                    "description": description,
                    "image": image
                }
            except Exception:
                link_preview = {"url": prefill_text}  # fallback: just pass the URL
        else:
            # Not a URL, just text
            link_preview = {"text": prefill_text}

    # --- Build final JSON response ---
    response_data = {
        "shared_file": shared_file or {"file": None, "content": None},
        "link_preview": link_preview or None
    }

    return JsonResponse(response_data)

'''
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

