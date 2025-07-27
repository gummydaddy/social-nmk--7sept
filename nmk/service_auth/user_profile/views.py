import os
import json
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
from .utils import linkify, hashtag_queue, add_to_fifo_list, make_usernames_clickable
import re
from django.db.models import F, Count, Q, Exists, OuterRef
from django.http import JsonResponse
from django.core.cache import cache
# from async_views import async_views

from .tasks import process_media_upload

#import pillow_heif
#pillow_heif.register_heif_opener()


from django.views.decorators.cache import cache_page
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


# Define constants for scoring weights
LIKED_HASHTAG_WEIGHT = 3
NOT_INTERESTED_HASHTAG_WEIGHT = -10
VIEWED_HASHTAG_WEIGHT = 2
SEARCH_HASHTAG_WEIGHT = 4
ACTIVE_USER_WEIGHT = 5
HIGH_ENGAGEMENT_WEIGHT = 3
CATEGORY_ENGAGEMENT_WEIGHT = 7
FRESHNESS_WEIGHT = 5
DIVERSITY_DECAY_RATE = 0.01
MAX_VIEWED_MEDIA_CACHE = 500
FALLBACK_MEDIA_COUNT = 24


def calculate_media_score(
    media,
    liked_hashtags,
    not_interested_hashtags,
    viewed_hashtags,
    search_hashtags,
    user_category_preferences,
    followed_users_media_ids=set(),
    followed_users_descriptions_matches=False
):
    score = 0
    media_hashtags = [h.name for h in media.hashtags.all()]

    # Apply weights based on hashtag preferences
    for hashtag in media_hashtags:
        if hashtag in liked_hashtags:
            score += LIKED_HASHTAG_WEIGHT
        if hashtag in not_interested_hashtags:
            score += NOT_INTERESTED_HASHTAG_WEIGHT
        if hashtag in viewed_hashtags:
            score += VIEWED_HASHTAG_WEIGHT
        if hashtag in search_hashtags:
            score += SEARCH_HASHTAG_WEIGHT

    # Boost if media was liked or viewed by user's followings
    if media.id in followed_users_media_ids:
        score += 10  # configurable boost

    # Boost if description matches user's hashtag interests
    if followed_users_descriptions_matches:
        score += 8  # configurable boost

    if hasattr(media, 'user') and hasattr(media.user, 'media'):
        user_post_count = media.user.media.count()
        if user_post_count > 10:
            score += ACTIVE_USER_WEIGHT

    if hasattr(media, 'likes_count') and media.likes_count > 50:
        score += HIGH_ENGAGEMENT_WEIGHT

    high_follower_users = set()
    if hasattr(media, 'likes'):
        high_follower_users.update(
            user for user in media.likes.all() if user.follower_set.count() > 100_000
        )

    if hasattr(media, 'views'):
        high_follower_users.update(
            view.user for view in media.views.all() if view.user.follower_set.count() > 100_000
        )

    if high_follower_users:
        score += 15

    if media.category in user_category_preferences:
        score += CATEGORY_ENGAGEMENT_WEIGHT

    return score




"""
# ---------------------------------------------------------------------------
# constants stay as‑is
LIKED_HASHTAG_WEIGHT      = 3
NOT_INTERESTED_HASHTAG_WEIGHT = -10
VIEWED_HASHTAG_WEIGHT     = 2
SEARCH_HASHTAG_WEIGHT     = 4
ACTIVE_USER_WEIGHT        = 5
HIGH_ENGAGEMENT_WEIGHT    = 3
CATEGORY_ENGAGEMENT_WEIGHT= 7
INFLUENCER_BONUS          = 15          # <— pulled literal 15 into a named const
# ---------------------------------------------------------------------------


    # ------------------------------------------------ influencer bump
    def has_big_follower_base(u):
        return getattr(u, "follower_total", u.follower_set.count()) > 100_000

    high_follower_users = {
        like.user for like in getattr(media, "likes", []).all() if has_big_follower_base(like.user)
    } | {
        view.user for view in getattr(media, "views", []).all() if has_big_follower_base(view.user)
    }

    if high_follower_users:
        score += INFLUENCER_BONUS

    # ------------------------------------------------ category preference
    if media.category in user_category_preferences:
        score += CATEGORY_ENGAGEMENT_WEIGHT

    return score
"""




import logging
logger = logging.getLogger(__name__)


'''
@login_required
def upload_media(request):
    logger.info(f"User {request.user.username} is uploading media")
    
    if request.method == 'POST':
        form = MediaForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info("MediaForm is valid.")
            media = form.save(commit=False)
            media.user = request.user

            # Assign the user's category to the media
            if request.user.profile.category:
                media.category = request.user.profile.category
                logger.info(f"Category '{media.category}' assigned to media by user {request.user.username}")
            else:
                logger.warning(f"User {request.user.username} has no category assigned in their profile")

            # Escape the description to prevent XSS attacks
            media.description = escape(media.description)

            # Determine if it's an image or video based on extension
            file_name = media.file.name.lower()
            if file_name.endswith(('.jpg', '.jpeg', '.png')):
                logger.info(f"Image file detected: {file_name}")
                media.media_type = 'image'
                filter_name = request.POST.get('filter')  # Optional filter for image
                media.save()  # Save the media instance
                # Send to Celery for image processing
                process_media_upload.delay(
                    media.id,
                    media.file.name,
                    'image',
                    filter_name
                )

            elif file_name.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                logger.info(f"Video file detected: {file_name}")
                media.media_type = 'video'
                media.save()
                # Send to Celery for video processing
                process_media_upload.delay(
                    media.id,
                    media.file.name,
                    'video'
                )

            else:
                logger.warning(f"Unknown file type uploaded: {file_name}")
                 media.save()

            # Redirect to user profile after successful upload
            return redirect('user_profile:profile', request.user.id)
        else:
            logger.warning("MediaForm is invalid.")
    else:
        form = MediaForm()

    return render(request, 'upload.html', {'form': form})
'''

@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
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

            if file_name.endswith(('.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic')):
                logger.info(f"Image file detected: {file_name}")
                media.media_type = 'image'
                media.is_processed = False  # Mark as unprocessed

                # Save media stub to DB (without file)
                media.save()
                form.save_m2m()

                # Save uploaded file to a temporary location
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp:
                        for chunk in file_obj.chunks():
                            temp.write(chunk)
                        temp_file_path = temp.name
                        logger.info(f"Temporary media file written to {temp_file_path}")
                except Exception as e:
                    logger.error(f"Failed to write temp file: {e}")
                    return JsonResponse({'status': 'temp_file_error'}, status=500)

                # Offload image processing to Celery
                process_media_upload.delay(
                    media.id,
                    temp_file_path,
                    file_name,
                    'image',
                    request.POST.get('filter')
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
                #profile_url = reverse('user_profile:profile', args=[request.user.id])
                #return JsonResponse({'status': 'success', 'redirect_url': profile_url})



            elif file_name.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                logger.info(f"Video file detected: {file_name}")
                return JsonResponse({'status': 'video_unsupported'}, status=400)

            else:
                logger.warning(f"Unknown file type uploaded: {file_name}")
                media.media_type = 'unknown'
                media.save()
                form.save_m2m()

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


@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
#@login_required  #username for future
def profile(request, user_id ):
    profile_user = get_object_or_404(AuthUser, id=user_id)

    # Fetch only necessary data
    followers_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()
    uploads_count = Media.objects.filter(user=profile_user).count()

    # Check if the user has an active story
    active_story = Story.objects.filter(user=profile_user, created_at__gt=timezone.now() - timezone.timedelta(hours=24)).first()
    #active_story = Story.objects.filter(user=profile_user, created_at__gt=timezone.now() - timezone.timedelta(hours=24))


    # Fetch media (thumbnails only) and exclude active story media
    media_qs = Media.objects.filter(user=profile_user).order_by('-created_at')
    if active_story:
        media_qs = media_qs.exclude(id=active_story.media.id)

    # Preload only necessary fields (avoid fetching full file data)
    media = media_qs.only('id', 'thumbnail', 'description', 'is_private')

    # Convert descriptions to clickable links
    for item in media:
        item.description = linkify(item.description)

    # Check blocking status
    is_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=profile_user).exists()
    is_blocked_by_profile_user = BlockedUser.objects.filter(blocker=profile_user, blocked=request.user).exists()
    
    if is_blocked_by_profile_user:
        return render(request, 'user_not_found.html')   

    # Relationship checks
    is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
    is_buddy = Buddy.objects.filter(user=profile_user, buddy=request.user).exists()

    # Filter media based on privacy
    filtered_media = [item for item in media if not item.is_private or is_buddy or request.user == profile_user]

    paginator = Paginator(filtered_media, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # If profile is private, restrict media visibility
    if profile_user.profile.is_private and not is_following and not is_buddy and request.user != profile_user:
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

    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'page_obj': page_obj,  # Only thumbnails are loaded
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


#@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
@cache_control(public=True, max_age=120, s_maxage=120)
def explore(request):
    user = request.user

    # Reset session and preference state
    if request.GET.get('reset') == '1':
        request.session.pop('explore_state', None)
        pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
        pref.viewed_media = []
        pref.save()
        cache.delete(f'user_{user.id}_explore_served_ids')  # Clear cache on reset
        return redirect('user_profile:explore')

    # User preferences
    pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
    liked_ht = pref.liked_hashtags or []
    not_int_ht = pref.not_interested_hashtags or []
    viewed_ht = pref.viewed_hashtags or []
    search_ht = pref.search_hashtags or []
    viewed_media_ids = pref.viewed_media or []
    not_int_media_ids = pref.not_interested_media or []
    liked_cats = pref.liked_categories or []

    hashtag_filter = request.GET.get('hashtag', '')
    q_filter = request.GET.get('q', '')

    blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)

    # Fetch served media IDs from cache
    served_cache_key = f'user_{user.id}_explore_served_ids'
    already_served_ids = set(cache.get(served_cache_key, []))

    media_qs = Media.objects.exclude(
        user__in=blocked_me
    ).exclude(
        user__in=i_blocked
    ).exclude(
        Q(is_private=True) & ~Q(user__buddy_list__buddy=user)
    ).exclude(
        Q(user__profile__is_private=True) &
        ~Q(user__buddy_list__buddy=user) &
        ~Q(user__follower_set__follower=user) &
        ~Q(user=user)
    ).exclude(
        id__in=already_served_ids
    ).annotate(
        likes_count=Count('likes', distinct=True)
    ).order_by('-created_at')

    if hashtag_filter:
        media_qs = media_qs.filter(hashtags__name__icontains=hashtag_filter)

    if q_filter:
        media_qs = media_qs.filter(
            Q(description__icontains=q_filter) |
            Q(hashtags__name__icontains=q_filter)
        ).distinct()

    media_qs = media_qs.exclude(id__in=not_int_media_ids)

    def score(media):
        base_score = calculate_media_score(
            media,
            liked_ht,
            not_int_ht,
            viewed_ht,
            search_ht,
            liked_cats
        )

        # Freshness score
        age_hours = (timezone.now() - media.created_at).total_seconds() / 3600
        base_score += max(FRESHNESS_WEIGHT - (age_hours * DIVERSITY_DECAY_RATE), 0)

        # Deprioritize own media
        if media.user_id == user.id:
            base_score -= 100

        return base_score

    media_ids = list(media_qs.values_list('id', flat=True)[:300])
    media_list = list(Media.objects.filter(id__in=media_ids).prefetch_related('hashtags', 'likes', 'user__media'))

    new_media = [m for m in media_list if m.id not in viewed_media_ids]
    old_media = [m for m in media_list if m.id in viewed_media_ids]

    SCORING_NOISE = 3.0

    def noisy_score(media):
        return score(media) + random.uniform(-SCORING_NOISE, SCORING_NOISE)

    scored_new = sorted(new_media, key=noisy_score, reverse=True)
    scored_old = sorted(old_media, key=noisy_score, reverse=True)

    sorted_media = scored_new + scored_old

    # Fallback if not enough content
    if len(sorted_media) < 12:
        fallback = Media.objects.exclude(
            id__in=not_int_media_ids + [m.id for m in sorted_media]
        ).annotate(
            likes_count=Count('likes')
        ).order_by('-likes_count', '-created_at')[:FALLBACK_MEDIA_COUNT]

        sorted_media += list(fallback)

    paginator = Paginator(sorted_media, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update viewed_media and cache served IDs
    """
    updated_viewed = False
    served_this_page = []

    for media in page_obj:
        if media.id not in viewed_media_ids:
            viewed_media_ids.append(media.id)
            updated_viewed = True
        served_this_page.append(media.id)

    if updated_viewed:
        pref.viewed_media = viewed_media_ids[-MAX_VIEWED_MEDIA_CACHE:]
        pref.save()

    updated_served_ids = list(already_served_ids.union(served_this_page))
    cache.set(served_cache_key, updated_served_ids, timeout=60 * 30)  # 30 mins
    """

    served_this_page = [media.id for media in page_obj]
    updated_served_ids = list(already_served_ids.union(served_this_page))
    cache.set(served_cache_key, updated_served_ids, timeout=60 * 30)  # 30 mins


    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_json = []
        for m in page_obj:
            media_data = {
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv')), # Use multiple extensions
                'thumbnail_url': m.thumbnail.url if m.thumbnail else None, 
                'explore_detail_url': reverse('user_profile:explore_detail', args=[m.id]), # Uncomment if you want to explicitly pass this URL
            }
            media_json.append(media_data)

        return JsonResponse({
            'media': media_json,
            'has_next': page_obj.has_next, # Crucial for telling the frontend if more pages exist
            'current_page': page_obj.number, # Can be useful for debugging or more complex logic
        }, headers={
            'Cache-Control': 'public, max-age=120, s-maxage=120'
        })
    

    return render(request, 'explore.html', {
        'page_obj': page_obj,
        'hashtag_filter': hashtag_filter,
        'q_filter': q_filter,
    })


@login_required
def search_uploads(request):
    query = request.GET.get('q', '').strip()
    hashtag_filter = request.GET.get('hashtag', '').strip()

    # Fetch user preferences
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags  # Include search hashtags
    viewed_media = user_hashtag_pref.viewed_media
    liked_categories = user_hashtag_pref.liked_categories

    # If there is a search query, add it to the search_hashtags list
    if query:
        user_hashtag_pref.add_search_hashtag(query)

    # Filter media by search query and hashtag filter
    media_objects = Media.objects.order_by('-created_at')

    if query: 
        media_objects = media_objects.filter(  
            Q(description__icontains=query) |
            Q(hashtags__name__icontains=query)
        ).distinct()

    if hashtag_filter:
        media_objects = media_objects.filter(hashtags__name__icontains=hashtag_filter)

    # Exclude media from users involved in blocking
    blocked_users = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    blocked_by_users = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)

    # Apply exclusion filters
    media_objects = media_objects.exclude(user__in=blocked_users)
    media_objects = media_objects.exclude(user__in=blocked_by_users)

    # Shuffle the media list for randomness
    media_list = list(media_objects)
    random.shuffle(media_list)

    # Calculate scores using the new scoring system
    media_scores = []
    for media in media_list:
        score = calculate_media_score(
            media,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags,  # Pass search hashtags to the scoring function
            liked_categories
        )
        media_scores.append((media, score))

    # Sort media by score (highest first)
    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    paginator = Paginator(sorted_media, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update viewed media
    for media in page_obj:
        if media.id not in viewed_media:
            viewed_media.append(media.id)
    user_hashtag_pref.viewed_media = viewed_media
    user_hashtag_pref.save()

    # Handle AJAX requests
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_list = [
            {
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.endswith('.mp4'),
                'user_username': m.user.username,
                'description': m.description
            }
            for m in page_obj
        ]
        return JsonResponse({'media': media_list})

    return render(request, 'explore.html', {
        'page_obj': page_obj,
        'query': query,
        'hashtag_filter': hashtag_filter
    })



#@vary_on_headers("X-Requested-With", "Authorization", "Cookie")
#@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
#@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def explore_detail(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user

    is_blocked_by_media_owner = BlockedUser.objects.filter(blocker=user, blocked=request.user).exists()
    has_blocked_media_owner = BlockedUser.objects.filter(blocker=request.user, blocked=user).exists()

    if is_blocked_by_media_owner:
        return render(request, 'user_not_found.html')

    is_following = Follow.objects.filter(follower=request.user, following=user).exists()
    is_buddy = Buddy.objects.filter(user=user, buddy=request.user).exists()

    if (media.is_private or user.profile.is_private) and not is_buddy and not is_following and request.user != user:
        return render(request, 'private_upload.html')

    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    viewed_media = user_hashtag_pref.viewed_media
    not_interested_media = user_hashtag_pref.not_interested_media
    liked_categories = user_hashtag_pref.liked_categories

    if media.id not in viewed_media:
        viewed_media.append(media.id)
        user_hashtag_pref.viewed_media = viewed_media
        user_hashtag_pref.save()

    description_hashtags = re.findall(r'#(\w+)', media.description)
    user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    is_video_main = media.file.url.endswith('.mp4')

    main_description_words = set(re.findall(r'\w+', media.description.lower()))

    # Cache key for related media viewed per media_id
    cache_key = f'user_{request.user.id}_related_viewed_{media_id}'
    related_already_sent_ids = set(cache.get(cache_key, []))

    # Related media query
    related_media = Media.objects.exclude(id=media_id).exclude(id__in=related_already_sent_ids)
    related_media = related_media.exclude(id__in=not_interested_media)

    users_blocked_me = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    related_media = related_media.exclude(user__in=users_blocked_me).exclude(user__in=users_i_blocked)

    related_media = related_media.exclude(
        Q(is_private=True) & ~Q(user__buddy_list__buddy=request.user)
    )

    related_media = related_media.exclude(
        Q(user__profile__is_private=True)
        & ~Q(user__buddy_list__buddy=request.user)
        & ~Q(user__follower_set__follower=request.user)
        & ~Q(user=request.user)
    )

    if liked_hashtags:
        related_media = related_media.annotate(
            num_liked_hashtags=Count(
                'hashtags',
                filter=Q(hashtags__name__in=liked_hashtags)
            )
        ).order_by('-num_liked_hashtags', '?')
    else:
        related_media = related_media.order_by('?')

    media_scores = []
    for related in related_media:
        score = calculate_media_score(
            related,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags,
            liked_categories
        )
        media_scores.append((related, score))

    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    related_media = [m[0] for m in sorted_media]

    # Paginate
    paginator = Paginator(related_media, 8)
    page = request.GET.get('page', 1)
    try:
        related_media_paginated = paginator.page(page)
    except PageNotAnInteger:
        related_media_paginated = paginator.page(1)
    except EmptyPage:
        related_media_paginated = paginator.page(paginator.num_pages)

    # Add viewed media to cache
    page_related_ids = [m.id for m in related_media_paginated]
    updated_related_ids = list(related_already_sent_ids.union(page_related_ids))
    cache.set(cache_key, updated_related_ids, timeout=60 * 30)  # 30 minutes cache

    if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
        media.view_count = F('view_count') + 1
        media.save(update_fields=['view_count'])
        Engagement.objects.create(media=media, user=request.user, engagement_type='view')

    description = make_usernames_clickable(media.description)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_data = {
            'id': media.id,
            'file_url': media.file.url,
            'is_video': media.file.url.endswith('.mp4'),
            'user_username': media.user.username,
            'description': description,
            'is_buddy': is_buddy,
            'is_following': is_following,
            'has_blocked_media_owner': has_blocked_media_owner,
            'is_blocked_by_media_owner': is_blocked_by_media_owner
        }
        related_media_list = [
            {
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.endswith('.mp4'),
                'user_username': m.user.username
            } for m in related_media_paginated
        ]
        return JsonResponse({'media': media_data, 'related_media': related_media_list})

    return render(request, 'explore_detail.html', {
        'media': media,
        'related_media': related_media_paginated,
        'description': description,
        'is_buddy': is_buddy,
        'is_following': is_following,
        'has_blocked_media_owner': has_blocked_media_owner,
        'is_blocked_by_media_owner': is_blocked_by_media_owner,
    })


'''
#@vary_on_headers("X-Requested-With", "Authorization", "Cookie")
@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def following_media(request):
    user = request.user

    # Cache current user's username
    username_cache_key = f'user_{user.id}_username'
    user_username = cache.get(username_cache_key)
    if not user_username:
        user_username = user.username
        cache.set(username_cache_key, user_username, timeout=60 * 10)

    # Get user's hashtag preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    liked_categories = user_hashtag_pref.liked_categories

    # Blocked users
    users_blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)

    # Followed users and buddies
    followed_users = AuthUser.objects.filter(
        follower_set__follower=user
    ).exclude(id__in=users_blocked_me).exclude(id__in=users_i_blocked)
    
    buddy_list = Buddy.objects.filter(user=user).values_list('buddy', flat=True)

    # Cache key for already served media
    served_media_cache_key = f'user_{user.id}_served_media_ids'
    already_sent_ids = set(cache.get(served_media_cache_key, []))

    # Media from followed users
    media_from_followed_users = Media.objects.filter(
        Q(user__in=followed_users) | Q(user__in=buddy_list)
    ).exclude(id__in=already_sent_ids).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags', 'likes'
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at').exclude(
        Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
    ).exclude(
        engagement__user=user, engagement__engagement_type='view'
    )

    # Explore media
    explore_media = Media.objects.exclude(
        user__in=users_blocked_me
    ).exclude(
        user__in=users_i_blocked
    ).exclude(
        id__in=already_sent_ids
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags', 'likes'
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at')

    combined_media = list(media_from_followed_users) + list(explore_media)

    # Score and filter
    media_scores = []
    for m in combined_media:
        score = calculate_media_score(
            m,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags,
            liked_categories
        )
        media_scores.append((m, score))

    sorted_media = sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    # Filter private & restricted media
    sorted_media = [
        m for m in sorted_media
        if not (
            m.is_private and not Buddy.objects.filter(user=m.user, buddy=user).exists() and user != m.user
        ) and not (
            m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists()
        )
    ]

    random.shuffle(sorted_media)
    """
    # View tracking updated for new view tracking
    for media in sorted_media:
        if not Engagement.objects.filter(user=user, media=media, engagement_type='view').exists():
            media.view_count = F('view_count') + 1
            media.save(update_fields=['view_count'])
            Engagement.objects.create(media=media, user=user, engagement_type='view')
    """

    # Enhance descriptions
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    # Pagination
    paginator = Paginator(sorted_media, 7)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update cache with media IDs from this page
    sent_ids = [m.id for m in page_obj]
    updated_sent_ids = list(already_sent_ids.union(sent_ids))
    cache.set(served_media_cache_key, updated_sent_ids, timeout=60 * 5)  # 30 min cache

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_list = []
        for m in page_obj:
            # Get profile picture URL or default
            try:
                profile_picture_url = m.user.profile.profile_picture.url
            except Exception:
                profile_picture_url = '/static/images/logo.png'

            media_list.append({
                'id': m.id,
                'file_url': m.file.url,
                'is_video': m.file.url.endswith('.mp4'),
                'user_username': user_username if m.user == user else m.user.username,
                'description': m.description,
                'likes_count': m.likes.count(),
                'is_liked': request.user in m.likes.all(),
                'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
                'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id':m.id}),
                'profile_url': reverse('user_profile:profile', kwargs={'user_id': m.user.id}),
                'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
                'profile_picture_url': profile_picture_url,  # ✅ added this
                #'view_tracking_url': reverse('user_profile:track_media_view', kwargs={'media_id': m.id})  # <-- Added


            })
        return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

    return render(request, 'following_media.html', {'page_obj': page_obj})
'''


@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def following_media(request):
    user = request.user

    # Cache current user's username
    username_cache_key = f'user_{user.id}_username'
    user_username = cache.get(username_cache_key)
    if not user_username:
        user_username = user.username
        cache.set(username_cache_key, user_username, timeout=60 * 10)

    # Get user's hashtag preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    liked_categories = user_hashtag_pref.liked_categories

    # Blocked users
    users_blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)

    # Followed users and buddies
    followed_users = AuthUser.objects.filter(
        follower_set__follower=user
    ).exclude(id__in=users_blocked_me).exclude(id__in=users_i_blocked)

    buddy_list = Buddy.objects.filter(user=user).values_list('buddy', flat=True)

    # Cache key for already served media
    served_media_cache_key = f'user_{user.id}_served_media_ids'
    already_sent_ids = set(cache.get(served_media_cache_key, []))

    # Media from followed users
    media_from_followed_users = Media.objects.filter(
        Q(user__in=followed_users) | Q(user__in=buddy_list)
    ).exclude(id__in=already_sent_ids).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags', 'likes'
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at').exclude(
        Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
    ).exclude(
        engagement__user=user, engagement__engagement_type='view'
    )

    # Explore media
    explore_media = Media.objects.exclude(
        user__in=users_blocked_me
    ).exclude(
        user__in=users_i_blocked
    ).exclude(
        id__in=already_sent_ids
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags', 'likes'
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(
            Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like')
        )
    ).order_by('-created_at')

    combined_media = list(media_from_followed_users) + list(explore_media)

    # Get media liked or viewed by followed users
    followed_users_ids = followed_users.values_list('id', flat=True)
    followed_users_prefs = UserHashtagPreference.objects.filter(user_id__in=followed_users_ids)

    followed_users_media_ids = set()
    followed_descriptions_keywords = set()

    for pref in followed_users_prefs:
        followed_users_media_ids.update(pref.viewed_media or [])
        followed_descriptions_keywords.update(pref.search_hashtags or [])
        followed_descriptions_keywords.update(pref.liked_hashtags or [])

    # Also get media liked by followed users from Engagements
    liked_media_by_followed = Engagement.objects.filter(
        user_id__in=followed_users_ids,
        engagement_type='like'
    ).values_list('media_id', flat=True)

    followed_users_media_ids.update(liked_media_by_followed)

    # Score and sort media
    media_scores = []
    for m in combined_media:
        description_lower = (m.description or "").lower()
        matched_description = any(tag.lower() in description_lower for tag in followed_descriptions_keywords)

        score = calculate_media_score(
            m,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags,
            liked_categories,
            followed_users_media_ids=followed_users_media_ids,
            followed_users_descriptions_matches=matched_description
        )
        media_scores.append((m, score))

    sorted_media = sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    # Filter private & restricted media
    sorted_media = [
        m for m in sorted_media
        if not (
            m.is_private and not Buddy.objects.filter(user=m.user, buddy=user).exists() and user != m.user
        ) and not (
            m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists()
        )
    ]

    random.shuffle(sorted_media)

    """
    # View tracking
    for media in sorted_media:
        if not Engagement.objects.filter(user=user, media=media, engagement_type='view').exists():
            media.view_count = F('view_count') + 1
            media.save(update_fields=['view_count'])
            Engagement.objects.create(media=media, user=user, engagement_type='view')
    """


    # Enhance descriptions
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    # Pagination
    paginator = Paginator(sorted_media, 7)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update served media cache
    sent_ids = [m.id for m in page_obj]
    updated_sent_ids = list(already_sent_ids.union(sent_ids))
    cache.set(served_media_cache_key, updated_sent_ids, timeout=60 * 5)

    # AJAX response
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
                'user_username': user_username if m.user == user else m.user.username,
                'description': m.description,
                'likes_count': m.likes.count(),
                'is_liked': request.user in m.likes.all(),
                'media_detail_url': reverse('user_profile:media_detail_view', kwargs={'media_id': m.id}),
                'explore_detail_url': reverse('user_profile:explore_detail', kwargs={'media_id': m.id}),
                'profile_url': reverse('user_profile:profile', kwargs={'user_id': m.user.id}),
                'like_url': reverse('user_profile:like_media', kwargs={'media_id': m.id}),
                'profile_picture_url': profile_picture_url,
                # 'view_tracking_url': reverse('user_profile:track_media_view', kwargs={'media_id': m.id})
            })

        return JsonResponse({'media': media_list, 'has_next': page_obj.has_next()})

    return render(request, 'following_media.html', {'page_obj': page_obj})



@login_required
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

        # ✅ Optionally: Mirror the same interaction in Engagement model
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


#to create likes
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


@login_required
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



#@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def media_detail_view(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user  # The owner of the media

    # Check if the current user is blocked by the media owner
    is_blocked_by_media_owner = BlockedUser.objects.filter(blocker=user, blocked=request.user).exists()

    # Check if the current user has blocked the media owner
    has_blocked_media_owner = BlockedUser.objects.filter(blocker=request.user, blocked=user).exists()

    # If the current user is blocked by the media owner, return a 'user_not_found' page
    if is_blocked_by_media_owner:
        return render(request, 'user_not_found.html')

    # Check if the current user is following the media owner
    is_following = Follow.objects.filter(follower=request.user, following=user).exists()

    # Check if the current user is in the media owner's buddy list
    is_buddy = Buddy.objects.filter(user=user, buddy=request.user).exists()

    # Check if the media is private and only buddies or the owner can view it
    if media.is_private and not is_buddy and request.user != user:
        return render(request, 'private_upload.html')

    # Check if the media is private, the user's profile is private, the current user is not a follower, and the current user is not the owner
    if (media.is_private or user.profile.is_private) and not is_following and request.user != user:
        return render(request, 'private_upload.html')

    # Fetch all older uploads by the media owner
    older_uploads = Media.objects.filter(user=user, created_at__lt=media.created_at)

    # Hide private media unless the viewer is the owner or a buddy of the owner
    if request.user != user and not is_buddy:
        older_uploads = older_uploads.filter(is_private=False)

    older_uploads = older_uploads.order_by('-created_at')

    # Paginate the user's older uploads
    paginator = Paginator(older_uploads, 8)  # Display 8 uploads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Engagement tracking (view count)
    if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
        media.view_count = F('view_count') + 1
        media.save(update_fields=['view_count'])
        Engagement.objects.create(media=media, user=request.user, engagement_type='view')

    # Hashtag preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    liked_categories = user_hashtag_pref.liked_categories
    viewed_media = user_hashtag_pref.viewed_media

    # Update viewed media and hashtags
    if media.id not in viewed_media:
        viewed_media.append(media.id)
        user_hashtag_pref.viewed_media = viewed_media
        user_hashtag_pref.save()

    description_hashtags = re.findall(r'#(\w+)', media.description)
    user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    # Making usernames clickable in the description
    description = make_usernames_clickable(media.description)

    # Context for rendering the media detail page
    context = {
        'media': media,
        'description': description,
        'is_following': is_following,
        'is_buddy': is_buddy,
        'has_blocked_media_owner': has_blocked_media_owner,
        'is_blocked_by_media_owner': is_blocked_by_media_owner,
        'page_obj': page_obj,  # Paginated older uploads

        # Add hashtag and category preferences to the context
        'liked_hashtags': liked_hashtags,
        'not_interested_hashtags': not_interested_hashtags,
        'viewed_hashtags': viewed_hashtags,
        'search_hashtags': search_hashtags,
        'liked_categories': liked_categories,
        'viewed_media': viewed_media,
    }

    return render(request, 'media_detail.html', context)



@login_required
def profile_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(notifications, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'profile_notifications.html', {'page_obj': page_obj})




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
def fetch_categories(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'categories': CATEGORY_CHOICES  # Return the choices as a list
        })
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
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


@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
def saved_uploads(request):
    profile = get_object_or_404(Profile, user=request.user)
    saved_media = profile.saved_uploads.all().order_by('-created_at')

    paginator = Paginator(saved_media, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'saved.html', {
        'page_obj': page_obj,
    })


@login_required
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


#@login_required
#def add_story(request):
#    if request.method == 'POST':
#        file = request.FILES.get('file')
#        user_description = request.POST.get('description', '')
#
#        # Prepend "story " to the description provided by the user
#        description = f"story {user_description.strip()}" if user_description else "story "
#
#        media = Media.objects.create(
#            user=request.user,
#            file=file,
#            description=description,
#            media_type=file.content_type.split('/')[0],
#            is_private=True
#        )
#        
#        story = Story.objects.create(user=request.user, media=media)
#        
#        # Redirect to the `view_story` page with the new story's id
#        return redirect('user_profile:view_story', story_id=story.id)
#
#    return render(request, 'add_story.html')


@cache_control(public=True, max_age=60, s_maxage=120, must_revalidate=True)
@login_required
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



@login_required
def toggle_privacy(request):
    profile = request.user.profile
    profile.is_private = not profile.is_private
    profile.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_private': profile.is_private})
    
    return redirect('user_profile:profile', user_id=request.user.id)


def toggle_media_privacy(request, media_id):
    media = get_object_or_404(Media, id=media_id, user=request.user)

    # Toggle the privacy status
    media.is_private = not media.is_private
    media.save()

    # Return the new privacy status as JSON
    return JsonResponse({'is_private': media.is_private})


@login_required
def add_to_buddy(request, user_id):
    """Add a user to the current user's buddy list."""
    user_to_add = get_object_or_404(AuthUser, id=user_id)
    
    # Ensure the user is following the current user before adding to buddy list (custom rule)
    Buddy.objects.get_or_create(user=request.user, buddy=user_to_add)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'added_to_buddy'})
    
    return redirect('user_profile:buddy_list')

    

@login_required
def buddy_list(request):
    """Display all users in the current user's buddy list."""
    buddies = Buddy.objects.filter(user=request.user).select_related('buddy')

    #buddy_users = [b.buddy for b in buddies]  # Get the actual User objects
    #return render(request, 'buddy_list.html', {'buddy_users': buddy_users})

    return render(request, 'buddy_list.html', {'buddies': buddies})


@login_required
def remove_from_buddy_list(request, user_id):
    """Remove a user from the current user's buddy list."""
    user_to_remove = get_object_or_404(AuthUser, id=user_id)
    buddy_relationship = Buddy.objects.filter(user=request.user, buddy=user_to_remove).first()

    if buddy_relationship:
        buddy_relationship.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'removed_from_buddy'})

    return redirect('user_profile:buddy_list')

