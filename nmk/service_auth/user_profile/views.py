import os
import json
from django.shortcuts import render, get_object_or_404, redirect
from PIL import Image, ImageFilter, ImageOps
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
from .forms import MediaForm, ProfileForm, CommentForm, AudioForm
from django.core.files.storage import get_storage_class
from .storage import CompressedMediaStorage

from service_auth.notion.forms import UsernameUpdateForm
from PIL import Image, ImageFilter, ImageOps
import io
import tempfile
from moviepy.editor import VideoFileClip, AudioFileClip
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from .serializers import MediaSerializer
from django.views.decorators.http import require_POST
from .utils import linkify, hashtag_queue, add_to_fifo_list, make_usernames_clickable
import re
from django.db.models import F, Count, Q, Exists, OuterRef
from django.http import JsonResponse
from django.core.cache import cache
# from async_views import async_views


from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
import asyncio


import random
from collections import deque
from django.template.loader import render_to_string
from django.utils.html import escape, mark_safe
from django.urls import reverse
from random import shuffle
# Define constants for scoring weights
LIKED_HASHTAG_WEIGHT = 3
NOT_INTERESTED_HASHTAG_WEIGHT = -10
VIEWED_HASHTAG_WEIGHT = 1
SEARCH_HASHTAG_WEIGHT = 2
ACTIVE_USER_WEIGHT = 2
HIGH_ENGAGEMENT_WEIGHT = 2

def calculate_media_score(media, liked_hashtags, not_interested_hashtags, viewed_hashtags, search_hashtags):
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

    # Check if the media object has the 'user' and 'media' attributes
    if hasattr(media, 'user') and hasattr(media.user, 'media'):
        user_post_count = media.user.media.count()
        if user_post_count > 10:
            score += ACTIVE_USER_WEIGHT

    # Check if the media object has the 'likes_count' attribute
    if hasattr(media, 'likes_count') and media.likes_count > 50:
        score += HIGH_ENGAGEMENT_WEIGHT

    return score




# @login_required
# def upload_media(request):
#     if request.method == 'POST':
#         form = MediaForm(request.POST, request.FILES)
#         if form.is_valid():
#             media = form.save(commit=False)
#             media.user = request.user

#             # Process description to make usernames clickable
#             # media.description = make_usernames_clickable(escape(media.description))
#             media.description = escape(media.description)
#             # media.description = make_usernames_clickable(media.description)
#             # media.description = linkify(media.description)

#             # Handle image uploads
#             if media.file.name.lower().endswith(('.jpg', '.jpeg', '.png')):
#                 media.media_type = 'image'
#                 image = Image.open(media.file)
#                 filter_name = request.POST.get('filter')
#                 if filter_name:
#                     filter_map = {
#                         'clarendon': ImageFilter.EMBOSS,
#                         'sepia': 'sepia',  # Custom filter
#                         'grayscale': 'grayscale',  # Custom filter
#                         'invert': ImageOps.invert,
#                     }
#                     if filter_name == 'sepia':
#                         sepia_image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
#                         image = sepia_image
#                     elif filter_name == 'grayscale':
#                         grayscale_image = ImageOps.grayscale(image)
#                         image = grayscale_image
#                     else:
#                         image = image.filter(filter_map.get(filter_name, ImageFilter.BLUR))

#                 byte_io = io.BytesIO()
#                 if image.mode == 'RGBA':
#                     image = image.convert('RGB')
#                 image.save(byte_io, format='JPEG')
#                 media.file = ContentFile(byte_io.getvalue(), media.file.name)

#             # Handle video uploads
#             elif media.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
#                 media.media_type = 'video'

#                 # Save the uploaded file to a temporary location
#                 with tempfile.NamedTemporaryFile(delete=False) as temp_file:
#                     for chunk in media.file.chunks():
#                         temp_file.write(chunk)
#                     temp_file_path = temp_file.name

#                 # Load the video clip
#                 clip = VideoFileClip(temp_file_path)

#                 # Get start time and duration from the form
#                 start_time = form.cleaned_data.get('start_time', 0)
#                 duration = form.cleaned_data.get('duration', clip.duration)

#                 # Validate and adjust start time and duration
#                 start_time = max(0, min(start_time, clip.duration))
#                 duration = max(0, min(duration, clip.duration - start_time))

#                 # Process video clip based on start_time and duration
#                 subclip = clip.subclip(start_time, start_time + duration)

#                 # Ensure the video is no longer than 90 seconds
#                 if subclip.duration > 90:
#                     subclip = subclip.subclip(0, 90)

#                 with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_output_file:
#                     output_file_path = temp_output_file.name

#                 subclip.write_videofile(output_file_path, codec='libx264', audio_codec='aac')
#                 subclip.close()

#                 with open(output_file_path, 'rb') as file:
#                     media.file = ContentFile(file.read(), media.file.name)

#             media.save()
#             form.save_m2m()  # Save tags
#             return redirect('user_profile:profile', request.user.id)
#     else:
#         form = MediaForm()
#     return render(request, 'upload.html', {'form': form})

import logging
logger = logging.getLogger(__name__)


@login_required
def upload_media(request):
    logger.info(f"User {request.user.username} is uploading media")
    if request.method == 'POST':
        form = MediaForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info("MediaForm is valid.")
            media = form.save(commit=False)
            media.user = request.user

            # Process description to make usernames clickable
            media.description = escape(media.description)

            # Use CompressedMediaStorage for saving the file
            storage = CompressedMediaStorage()

            # Handle image uploads
            if media.file.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                logger.info(f"Image file detected: {media.file.name}")
                media.media_type = 'image'
                image = Image.open(media.file)
                filter_name = request.POST.get('filter')
                if filter_name:
                    logger.info(f"Applying filter: {filter_name} to image: {media.file.name}")
                    filter_map = {
                        'clarendon': ImageFilter.EMBOSS,
                        'sepia': 'sepia',  # Custom filter
                        'grayscale': 'grayscale',  # Custom filter
                        'invert': ImageOps.invert,
                    }
                    if filter_name == 'sepia':
                        sepia_image = ImageOps.colorize(image.convert("L"), "#704214", "#C0C090")
                        image = sepia_image
                    elif filter_name == 'grayscale':
                        grayscale_image = ImageOps.grayscale(image)
                        image = grayscale_image
                    else:
                        image = image.filter(filter_map.get(filter_name, ImageFilter.BLUR))

                byte_io = io.BytesIO()
                if image.mode == 'RGBA':
                    image = image.convert('RGB')
                image.save(byte_io, format='JPEG')
                media.file = ContentFile(byte_io.getvalue(), media.file.name)

            # Handle video uploads
            elif media.file.name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                logger.info(f"Video file detected: {media.file.name}")
                media.media_type = 'video'

                # Save the uploaded file to a temporary location
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    for chunk in media.file.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name

                # Load the video clip
                clip = VideoFileClip(temp_file_path)

                # Get start time and duration from the form
                start_time = form.cleaned_data.get('start_time', 0)
                duration = form.cleaned_data.get('duration', clip.duration)

                # Validate and adjust start time and duration
                start_time = max(0, min(start_time, clip.duration))
                duration = max(0, min(duration, clip.duration - start_time))

                logger.info(f"Processing video: {media.file.name} with start_time={start_time} and duration={duration}")

                # Process video clip based on start_time and duration
                subclip = clip.subclip(start_time, start_time + duration)

                # Ensure the video is no longer than 90 seconds
                if subclip.duration > 90:
                    subclip = subclip.subclip(0, 90)

                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_output_file:
                    output_file_path = temp_output_file.name

                subclip.write_videofile(output_file_path, codec='libx264', audio_codec='aac')
                subclip.close()

                with open(output_file_path, 'rb') as file:
                    media.file = ContentFile(file.read(), media.file.name)

            else:
                logger.warning(f"Unknown file type uploaded: {media.file.name}")

            try:
                media.file.name = storage.save(media.file.name, media.file)
                media.save()
                logger.info(f"Media file {media.file.name} saved successfully for user {request.user.username}")
                form.save_m2m()  # Save tags
                return redirect('user_profile:profile', request.user.id)
            except Exception as e:
                logger.error(f"Error saving media file {media.file.name}: {e}")
        else:
            logger.warning("MediaForm is invalid.")
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
def voices(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)

    # Fetch all audio uploads, ordered by creation date
    audio_files = Audio.objects.all().order_by('-created_at')

    # Filter audio based on privacy and relationship to the user
    filtered_audio = []
    for audio in audio_files:
        if audio.is_private and audio.user != request.user and not audio.tags.filter(id=request.user.id).exists():
            continue
        filtered_audio.append(audio)

    # Paginate the results, 100 audio files per page
    paginator = Paginator(filtered_audio, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the voices.html template and pass context
    return render(request, 'voices.html', {
        'page_obj': page_obj,
        'audio_count': Audio.objects.count(),
        'profile_user': profile_user,
    })



@login_required
def media_tags(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    tagged_media = Media.objects.filter(tags=profile_user).order_by('-created_at')
    paginator = Paginator(tagged_media, 100)  # Paginate the results
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'media_tags.html', {
        'profile_user': profile_user,
        'page_obj': page_obj,
    })


# @login_required
# def profile(request, user_id):
#     profile_user = get_object_or_404(AuthUser, id=user_id)
     


#     media = Media.objects.filter(user=profile_user).order_by('-created_at')
#     followers_count = Follow.objects.filter(following=profile_user).count()
#     following_count = Follow.objects.filter(follower=profile_user).count()
#     uploads_count = Media.objects.filter(user=profile_user).count()


#     # Check if the user has an active story
#     active_story = Story.objects.filter(user=profile_user, created_at__gt=timezone.now() - timezone.timedelta(hours=24)).first()

#     # Exclude media associated with the active story
#     if active_story:
#         media = Media.objects.filter(user=profile_user).exclude(id=active_story.media.id).order_by('-created_at')
#     else:
#         media = Media.objects.filter(user=profile_user).order_by('-created_at')


#     for item in media:
#         item.description = linkify(item.description)

#     # Check if the current user has blocked this profile user
#     is_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=profile_user).exists()
    
#     # Check if the profile user has blocked the current user
#     is_blocked_by_profile_user = BlockedUser.objects.filter(blocker=profile_user, blocked=request.user).exists()
    
#     if is_blocked_by_profile_user:
#         return render(request, 'user_not_found.html')   
    

#     paginator = Paginator(media, 100)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     # Check if the current user is following the profile user
#     is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()

#      # Check if the profile is private and the current user is not following
#     if profile_user.profile.is_private and not is_following and request.user != profile_user:
#         return render(request, 'profile.html', {
#         'profile_user': profile_user,
#         # 'page_obj': page_obj,
#         'followers_count': followers_count,
#         'following_count': following_count,
#         'uploads_count': uploads_count,
#         'is_following': is_following,
#         # 'active_story': active_story,
#         'is_blocked': is_blocked,
#     })  # Render a page that shows the profile is private
        

#     return render(request, 'profile.html', {
#         'profile_user': profile_user,
#         'page_obj': page_obj,
#         'followers_count': followers_count,
#         'following_count': following_count,
#         'uploads_count': uploads_count,
#         'is_following': is_following,
#         'active_story': active_story,
#         'is_blocked': is_blocked,
#     })


@login_required
def profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)

    # Fetch all media uploads of the profile user
    media = Media.objects.filter(user=profile_user).order_by('-created_at')

    followers_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()
    uploads_count = Media.objects.filter(user=profile_user).count()

    # Check if the user has an active story
    active_story = Story.objects.filter(user=profile_user, created_at__gt=timezone.now() - timezone.timedelta(hours=24)).first()

    # Exclude media associated with the active story
    if active_story:
        media = Media.objects.filter(user=profile_user).exclude(id=active_story.media.id).order_by('-created_at')
    else:
        media = Media.objects.filter(user=profile_user).order_by('-created_at')

    for item in media:
        item.description = linkify(item.description)

    # Check if the current user has blocked this profile user
    is_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=profile_user).exists()
    
    # Check if the profile user has blocked the current user
    is_blocked_by_profile_user = BlockedUser.objects.filter(blocker=profile_user, blocked=request.user).exists()
    
    if is_blocked_by_profile_user:
        return render(request, 'user_not_found.html')   

    # Check if the current user is following the profile user
    is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()

    # Check if the current user is in the profile user's buddy list
    is_buddy = Buddy.objects.filter(user=profile_user, buddy=request.user).exists()

    # Filter media based on privacy and relationship
    filtered_media = []
    for item in media:
        if item.is_private and not is_buddy and request.user != profile_user:
            continue
        filtered_media.append(item)

    # Filter private media for users not in buddy list
    private_media = [item for item in media if item.is_private and not is_buddy and request.user != profile_user]

    paginator = Paginator(filtered_media, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Check if the profile is private and the current user is not following or buddy
    if profile_user.profile.is_private and not is_following and not is_buddy and request.user != profile_user:
        return render(request, 'profile.html', {
            'profile_user': profile_user,
            # 'page_obj': page_obj,
            'followers_count': followers_count,
            'following_count': following_count,
            'uploads_count': uploads_count,
            'is_following': is_following,
            'is_buddy': is_buddy,
            # 'active_story': active_story,
            'is_blocked': is_blocked,
            'private_media': private_media,  # Pass private media to template
        })  # Render a page that shows the profile is private

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
        'private_media': [],  # Pass empty list for users in buddy list
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


# @login_required
# def explore(request):
#     user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
#     liked_hashtags = user_hashtag_pref.liked_hashtags
#     not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
#     viewed_hashtags = user_hashtag_pref.viewed_hashtags
#     viewed_media = user_hashtag_pref.viewed_media
#     not_interested_media = user_hashtag_pref.not_interested_media  # Media IDs the user marked as not interested

#     hashtag_filter = request.GET.get('hashtag', '')

#     # Get users who have blocked the current user
#     users_blocked_me = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
#     users_i_blocked = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)

#     # Fetch media and exclude media from users who have blocked the current user
#     media_objects = Media.objects.order_by('-created_at').exclude(
#         user__in=users_blocked_me
#     ).exclude(
#         user__in=users_i_blocked
#     )

#     # Exclude private media if the media owner has not added the current user as a buddy
#     media_objects = media_objects.exclude(
#         Q(is_private=True) & ~Q(user__buddy_list__buddy=request.user)
#     )

#     # Exclude media from private profiles if the current user is not a buddy or follower
#     media_objects = media_objects.exclude(
#         Q(user__profile__is_private=True) & ~Q(user__buddy_list__buddy=request.user) & ~Q(user__follower_set__follower=request.user) & ~Q(user=request.user)
#     )

#     # Filter by hashtag if a hashtag filter is provided
#     if hashtag_filter:
#         media_objects = media_objects.filter(hashtags__name__icontains=hashtag_filter)

#     # Exclude media that the user marked as not interested
#     media_objects = media_objects.exclude(id__in=not_interested_media)

#     # Shuffle and score media based on user preferences
#     media_list = list(media_objects)
#     random.shuffle(media_list)

#     new_media = [media for media in media_list if media.id not in viewed_media]
#     old_media = [media for media in media_list if media.id in viewed_media]

#     media_scores = []
#     for media in new_media + old_media:
#         score = 0
#         media_hashtags = [h.name for h in media.hashtags.all()]
#         description_hashtags = re.findall(r'#(\w+)', media.description)

#         # Increase/decrease score based on user's hashtag preferences
#         for hashtag in media_hashtags + description_hashtags:
#             if hashtag in liked_hashtags:
#                 score += 1.5
#             if hashtag in viewed_hashtags:
#                 score += 0.9
#             if hashtag in not_interested_hashtags:
#                 score -= 8  # Penalize media containing "not interested" hashtags

#         media_scores.append((media, score))

#     # Sort media by score (highest first)
#     sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
#     sorted_media = [m[0] for m in sorted_media]

#     # Paginate media results
#     paginator = Paginator(sorted_media, 100)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     # Update the user's viewed media list
#     for media in page_obj:
#         if media.id not in viewed_media:
#             viewed_media.append(media.id)
#     user_hashtag_pref.viewed_media = viewed_media
#     user_hashtag_pref.save()

#     # Return JSON response for AJAX requests
#     if request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         media_list = [
#             {
#                 'id': m.id,
#                 'file_url': m.file.url,
#                 'is_video': m.file.url.endswith('.mp4'),
#                 'user_username': m.user.username,
#                 'description': m.description
#             }
#             for m in page_obj
#         ]
#         return JsonResponse({'media': media_list})

#     # Render the explore page for normal requests
#     return render(request, 'explore.html', {
#         'page_obj': page_obj,
#         'hashtag_filter': hashtag_filter
#     })


@login_required
def explore(request):
    # Fetch or create the user's hashtag preferences
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    viewed_media = user_hashtag_pref.viewed_media
    not_interested_media = user_hashtag_pref.not_interested_media  # Media IDs the user marked as not interested

    hashtag_filter = request.GET.get('hashtag', '')

    # Get users who have blocked the current user
    users_blocked_me = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)

    # Fetch media and exclude media from users who have blocked the current user
    media_objects = Media.objects.order_by('-created_at').exclude(
        user__in=users_blocked_me
    ).exclude(
        user__in=users_i_blocked
    )

    # Exclude private media if the media owner has not added the current user as a buddy
    media_objects = media_objects.exclude(
        Q(is_private=True) & ~Q(user__buddy_list__buddy=request.user)
    )

    # Exclude media from private profiles if the current user is not a buddy or follower
    media_objects = media_objects.exclude(
        Q(user__profile__is_private=True) & ~Q(user__buddy_list__buddy=request.user) & ~Q(user__follower_set__follower=request.user) & ~Q(user=request.user)
    )

    # Filter by hashtag if a hashtag filter is provided
    if hashtag_filter:
        media_objects = media_objects.filter(hashtags__name__icontains=hashtag_filter)

    # Exclude media that the user marked as not interested
    media_objects = media_objects.exclude(id__in=not_interested_media)

    # Shuffle the media list for randomness
    media_list = list(media_objects)
    random.shuffle(media_list)

    # Split media into new and old based on whether it has been viewed
    new_media = [media for media in media_list if media.id not in viewed_media]
    old_media = [media for media in media_list if media.id in viewed_media]

    # Calculate scores for media
    media_scores = []
    for media in new_media + old_media:
        score = calculate_media_score(media, liked_hashtags, not_interested_hashtags, viewed_hashtags, search_hashtags)
        media_scores.append((media, score))

    # Sort media by score (highest first)
    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    # Paginate media results
    paginator = Paginator(sorted_media, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Update the user's viewed media list
    for media in page_obj:
        if media.id not in viewed_media:
            viewed_media.append(media.id)
    user_hashtag_pref.viewed_media = viewed_media
    user_hashtag_pref.save()

    # Return JSON response for AJAX requests
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

    # Render the explore page for normal requests
    return render(request, 'explore.html', {
        'page_obj': page_obj,
        'hashtag_filter': hashtag_filter
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
            search_hashtags  # Pass search hashtags to the scoring function
        )
        media_scores.append((media, score))

    # Sort media by score (highest first)
    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    paginator = Paginator(sorted_media, 100)
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




# @login_required
# def explore_detail(request, media_id):
#     media = get_object_or_404(Media, id=media_id)
#     user = media.user  # The owner of the media

#     # Check if the current user is blocked by the media owner
#     is_blocked_by_media_owner = BlockedUser.objects.filter(blocker=user, blocked=request.user).exists()

#     # Check if the current user has blocked the media owner
#     has_blocked_media_owner = BlockedUser.objects.filter(blocker=request.user, blocked=user).exists()

#     # If the current user is blocked by the media owner, return a 'user_not_found' or restricted view page
#     if is_blocked_by_media_owner:
#         return render(request, 'user_not_found.html')  # Show an "upload not found" message

#     # Check if the current user is following the media owner
#     is_following = Follow.objects.filter(follower=request.user, following=user).exists()

#     # Check if the current user is in the media owner's buddy list
#     is_buddy = Buddy.objects.filter(user=user, buddy=request.user).exists()

#     # Check if the media is private, and the current user is not allowed to view it
#     # The current user can view it only if they are in the buddy list or they are the media owner
#     if (media.is_private or user.profile.is_private) and not is_buddy and not is_following and request.user != user:
#         return render(request, 'private_upload.html')  # Show an "upload is private" message

#     # User hashtag preference (tracking viewed media and hashtags)
#     user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
#     liked_hashtags = user_hashtag_pref.liked_hashtags
#     viewed_hashtags = user_hashtag_pref.viewed_hashtags
#     viewed_media = user_hashtag_pref.viewed_media
#     not_interested_media = user_hashtag_pref.not_interested_media  # Add this line

#     # Update viewed media and hashtags
#     if media.id not in viewed_media:
#         viewed_media.append(media.id)
#         user_hashtag_pref.viewed_media = viewed_media
#         user_hashtag_pref.save()

#     description_hashtags = re.findall(r'#(\w+)', media.description)
#     user_hashtag_pref.add_viewed_hashtag(description_hashtags)

#     # Related media logic
#     related_media = Media.objects.exclude(id=media_id)

#     # Exclude media marked as not interested by the current user (new constraint)
#     related_media = related_media.exclude(id__in=not_interested_media)

#     # Exclude related media from users who have blocked the current user
#     users_blocked_me = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
#     users_i_blocked = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
#     related_media = related_media.exclude(user__in=users_blocked_me).exclude(user__in=users_i_blocked)

#     # Exclude private media from users who are not in the current user's buddy list or followers
#     related_media = related_media.exclude(
#         Q(is_private=True) & ~Q(user__buddy_list__buddy=request.user)
#     )

#     # Exclude all media from users with private profiles if the current user is not a buddy or follower
#     related_media = related_media.exclude(
#         Q(user__profile__is_private=True) & ~Q(user__buddy_list__buddy=request.user) & ~Q(user__follower_set__follower=request.user) & ~Q(user=request.user)
#     )

#     # Filter related media by liked hashtags
#     if liked_hashtags:
#         related_media = related_media.annotate(
#             num_liked_hashtags=Count(
#                 'hashtags',
#                 filter=Q(hashtags__name__in=liked_hashtags)
#             )
#         ).order_by('-num_liked_hashtags', '?')
#     else:
#         related_media = related_media.order_by('?')

#     # Scoring system
#     media_scores = []
#     for related in related_media:
#         score = 0
#         media_hashtags = [h.name for h in related.hashtags.all()]
#         description_hashtags = re.findall(r'#(\w+)', related.description)

#         # Increase/decrease score based on user's hashtag preferences
#         for hashtag in media_hashtags + description_hashtags:
#             if hashtag in liked_hashtags:
#                 score += 1.5
#             if hashtag in viewed_hashtags:
#                 score += 0.9
#             if hashtag in user_hashtag_pref.not_interested_hashtags:
#                 score -= 8  # Penalize media containing "not interested" hashtags

#         media_scores.append((related, score))

#     # Sort related media by score
#     sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
#     related_media = [m[0] for m in sorted_media][:100]

#     # Engagement tracking
#     if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
#         media.view_count = F('view_count') + 1
#         media.save(update_fields=['view_count'])
#         Engagement.objects.create(media=media, user=request.user, engagement_type='view')

#     # Making usernames clickable in the description
#     description = make_usernames_clickable(media.description)

#     if request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         media_data = {
#             'id': media.id,
#             'file_url': media.file.url,
#             'is_video': media.file.url.endswith('.mp4'),
#             'user_username': media.user.username,
#             'description': description,
#             'is_buddy': is_buddy,
#             'is_following': is_following,
#             'has_blocked_media_owner': has_blocked_media_owner,
#             'is_blocked_by_media_owner': is_blocked_by_media_owner
#         }
#         related_media_list = [
#             {
#                 'id': m.id,
#                 'file_url': m.file.url,
#                 'is_video': m.file.url.endswith('.mp4'),
#                 'user_username': m.user.username
#             } for m in related_media
#         ]
#         return JsonResponse({'media': media_data, 'related_media': related_media_list})

#     return render(request, 'explore_detail.html', {
#         'media': media,
#         'related_media': related_media,
#         'description': description,
#         'is_buddy': is_buddy,
#         'is_following': is_following,
#         'has_blocked_media_owner': has_blocked_media_owner,
#         'is_blocked_by_media_owner': is_blocked_by_media_owner
#     })


@login_required
def explore_detail(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user = media.user  # The owner of the media

    # Check if the current user is blocked by the media owner
    is_blocked_by_media_owner = BlockedUser.objects.filter(blocker=user, blocked=request.user).exists()

    # Check if the current user has blocked the media owner
    has_blocked_media_owner = BlockedUser.objects.filter(blocker=request.user, blocked=user).exists()

    # If the current user is blocked by the media owner, return a 'user_not_found' or restricted view page
    if is_blocked_by_media_owner:
        return render(request, 'user_not_found.html')  # Show an "upload not found" message

    # Check if the current user is following the media owner
    is_following = Follow.objects.filter(follower=request.user, following=user).exists()

    # Check if the current user is in the media owner's buddy list
    is_buddy = Buddy.objects.filter(user=user, buddy=request.user).exists()

    # Check if the media is private, and the current user is not allowed to view it
    # The current user can view it only if they are in the buddy list or they are the media owner
    if (media.is_private or user.profile.is_private) and not is_buddy and not is_following and request.user != user:
        return render(request, 'private_upload.html')  # Show an "upload is private" message

    # User hashtag preference (tracking viewed media and hashtags)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags
    viewed_media = user_hashtag_pref.viewed_media
    not_interested_media = user_hashtag_pref.not_interested_media  # Media IDs the user marked as not interested

    # Update viewed media and hashtags
    if media.id not in viewed_media:
        viewed_media.append(media.id)
        user_hashtag_pref.viewed_media = viewed_media
        user_hashtag_pref.save()

    description_hashtags = re.findall(r'#(\w+)', media.description)
    user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    # Related media logic
    related_media = Media.objects.exclude(id=media_id)

    # Exclude media marked as not interested by the current user (new constraint)
    related_media = related_media.exclude(id__in=not_interested_media)

    # Exclude related media from users who have blocked the current user
    users_blocked_me = BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    related_media = related_media.exclude(user__in=users_blocked_me).exclude(user__in=users_i_blocked)

    # Exclude private media from users who are not in the current user's buddy list or followers
    related_media = related_media.exclude(
        Q(is_private=True) & ~Q(user__buddy_list__buddy=request.user)
    )

    # Exclude all media from users with private profiles if the current user is not a buddy or follower
    related_media = related_media.exclude(
        Q(user__profile__is_private=True) & ~Q(user__buddy_list__buddy=request.user) & ~Q(user__follower_set__follower=request.user) & ~Q(user=request.user)
    )

    # Filter related media by liked hashtags and order them by the count of liked hashtags
    if liked_hashtags:
        related_media = related_media.annotate(
            num_liked_hashtags=Count(
                'hashtags',
                filter=Q(hashtags__name__in=liked_hashtags)
            )
        ).order_by('-num_liked_hashtags', '?')
    else:
        related_media = related_media.order_by('?')

    # Apply the scoring system
    media_scores = []
    for related in related_media:
        score = calculate_media_score(
            related,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags
        )
        media_scores.append((related, score))

    # Sort related media by score
    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    related_media = [m[0] for m in sorted_media][:100]

    # Engagement tracking
    if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
        media.view_count = F('view_count') + 1
        media.save(update_fields=['view_count'])
        Engagement.objects.create(media=media, user=request.user, engagement_type='view')

    # Making usernames clickable in the description
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
            } for m in related_media
        ]
        return JsonResponse({'media': media_data, 'related_media': related_media_list})

    return render(request, 'explore_detail.html', {
        'media': media,
        'related_media': related_media,
        'description': description,
        'is_buddy': is_buddy,
        'is_following': is_following,
        'has_blocked_media_owner': has_blocked_media_owner,
        'is_blocked_by_media_owner': is_blocked_by_media_owner
    })





# @login_required
# def following_media(request):
#     user = request.user

#     # Fetch or create the user's hashtag preferences
#     user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
#     liked_hashtags = user_hashtag_pref.liked_hashtags
#     not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
#     viewed_hashtags = user_hashtag_pref.viewed_hashtags

#     # Get users who have blocked the current user
#     users_blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
#     users_i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)

#     # Get users that the current user is following
#     followed_users = AuthUser.objects.filter(
#         follower_set__follower=user
#     ).exclude(
#         id__in=users_blocked_me
#     ).exclude(
#         id__in=users_i_blocked
#     )

#     # Get buddy list
#     buddy_list = Buddy.objects.filter(user=user).values_list('buddy', flat=True)

#     # Fetch media from followed users and buddies
#     media_from_followed_users = Media.objects.filter(
#         Q(user__in=followed_users) | Q(user__in=buddy_list)
#     ).select_related(
#         'user', 'user__profile'
#     ).prefetch_related(
#         'hashtags',  # Prefetch hashtags associated with each media
#         'likes'  # Prefetch likes for calculating engagement levels
#     ).annotate(
#         likes_count=Count('likes'),
#         is_liked=Exists(Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like'))
#     ).order_by('-created_at').exclude(
#         Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
#     ).exclude(
#         engagement__user=user, engagement__engagement_type='view'
#     )

#     # If no media from followed users, use the explore logic
#     explore_media = Media.objects.exclude(
#         user__in=users_blocked_me
#     ).exclude(
#         user__in=users_i_blocked
#     ).select_related(
#         'user', 'user__profile'
#     ).prefetch_related(
#         'hashtags', 'likes'
#     ).annotate(
#         likes_count=Count('likes'),
#         is_liked=Exists(Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like'))
#     ).order_by('-created_at')

#     # Combine all media from followed users and the explore logic
#     combined_media = list(media_from_followed_users) + list(explore_media)

#     # Apply scoring and constraints
#     media_scores = []
#     for m in combined_media:
#         score = 0
#         media_hashtags = [h.name for h in m.hashtags.all()]

#         # Apply hashtag preferences scoring
#         for hashtag in media_hashtags:
#             if hashtag in liked_hashtags:
#                 score += 1
#             if hashtag in not_interested_hashtags:
#                 score -= 8
#             if hashtag in viewed_hashtags:
#                 score += 0.9  # Adjust this weight as needed

#         # Boost score based on user activity frequency (number of media posts by the user)
#         user_post_count = m.user.media.count()  # Counting user's media posts
#         if user_post_count > 10:
#             score += 2  # Boost for active users who post frequently

#         # Boost score based on engagement levels (likes count as engagement)
#         if m.likes_count > 50:
#             score += 1.5  # Boost for media with high engagement levels

#         # Add media and its score to the list
#         media_scores.append((m, score))

#     # Sort by score and creation date (newest first)
#     sorted_media = sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)
#     sorted_media = [m[0] for m in sorted_media]

#     # Apply private media constraints
#     sorted_media = [m for m in sorted_media 
#                     if not (m.is_private and m.user.id not in buddy_list and user != m.user)
#                     and not (m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists())]

#     # Randomize the order while keeping the newest media first
#     random.shuffle(sorted_media)

#     # Track engagement for viewed media
#     for media in sorted_media:
#         # Check if the current user has already viewed this media
#         if not Engagement.objects.filter(user=user, media=media, engagement_type='view').exists():
#             # Increment view count and save the media
#             media.view_count = F('view_count') + 1
#             media.save(update_fields=['view_count'])

#             # Create a view engagement entry
#             Engagement.objects.create(media=media, user=user, engagement_type='view')

#     # Apply make_usernames_clickable to descriptions
#     for media in sorted_media:
#         media.description = make_usernames_clickable(media.description)

#     paginator = Paginator(sorted_media, 8)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     if request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         media_list = [
#             {
#                 'id': m.id,
#                 'file_url': m.file.url,
#                 'is_video': m.file.url.endswith('.mp4'),
#                 'user_username': m.user.username,
#                 'description': m.description
#             }
#             for m in page_obj
#         ]
#         return JsonResponse({'media': media_list})

#     return render(request, 'following_media.html', {'page_obj': page_obj})



@login_required
def following_media(request):
    user = request.user
    
    # Fetch or create the user's hashtag preferences
    user_hashtag_pref, _ = UserHashtagPreference.objects.get_or_create(user=user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    search_hashtags = user_hashtag_pref.search_hashtags  # Include search hashtags
    
    # Get users who have blocked the current user
    users_blocked_me = BlockedUser.objects.filter(blocked=user).values_list('blocker', flat=True)
    users_i_blocked = BlockedUser.objects.filter(blocker=user).values_list('blocked', flat=True)
    
    # Get users that the current user is following
    followed_users = AuthUser.objects.filter(
        follower_set__follower=user
    ).exclude(
        id__in=users_blocked_me
    ).exclude(
        id__in=users_i_blocked
    )
    
    # Get buddy list
    buddy_list = Buddy.objects.filter(user=user).values_list('buddy', flat=True)
    
    # Fetch media from followed users and buddies
    media_from_followed_users = Media.objects.filter(
        Q(user__in=followed_users) | Q(user__in=buddy_list)
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags',  # Prefetch hashtags associated with each media
        'likes'  # Prefetch likes for calculating engagement levels
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like'))
    ).order_by('-created_at').exclude(
        Q(is_private=True) & ~Q(user__in=buddy_list) & ~Q(user=user)
    ).exclude(
        engagement__user=user, engagement__engagement_type='view'
    )

    # If no media from followed users, use the explore logic
    explore_media = Media.objects.exclude(
        user__in=users_blocked_me
    ).exclude(
        user__in=users_i_blocked
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'hashtags', 'likes'
    ).annotate(
        likes_count=Count('likes'),
        is_liked=Exists(Engagement.objects.filter(media=OuterRef('id'), user=user, engagement_type='like'))
    ).order_by('-created_at')

    # Combine all media from followed users and the explore logic
    combined_media = list(media_from_followed_users) + list(explore_media)

    # Apply scoring and constraints
    media_scores = []
    for m in combined_media:
        score = calculate_media_score(
            m,
            liked_hashtags,
            not_interested_hashtags,
            viewed_hashtags,
            search_hashtags  # Pass search hashtags to the scoring function
        )
        media_scores.append((m, score))

    # Sort by score and creation date (newest first)
    sorted_media = sorted(media_scores, key=lambda x: (x[1], x[0].created_at), reverse=True)
    sorted_media = [m[0] for m in sorted_media]

    # Apply private media constraints
    sorted_media = [m for m in sorted_media 
                    if not (m.is_private and m.user.id not in buddy_list and user != m.user)
                    and not (m.user.profile.is_private and not m.user.follower_set.filter(follower=user).exists())]

    # Randomize the order while keeping the newest media first
    random.shuffle(sorted_media)

    # Track engagement for viewed media
    for media in sorted_media:
        if not Engagement.objects.filter(user=user, media=media, engagement_type='view').exists():
            media.view_count = F('view_count') + 1
            media.save(update_fields=['view_count'])
            Engagement.objects.create(media=media, user=user, engagement_type='view')

    # Apply make_usernames_clickable to descriptions
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    paginator = Paginator(sorted_media, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

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


# @csrf_exempt
# @require_POST
# def log_interaction(request):
#     try:
#         # Log the request body for debugging
#         print(f"Request body: {request.body}")

#         if not request.content_type == 'application/json':
#             return JsonResponse({'error': 'Invalid content type'}, status=400)

#         # Parse the JSON payload
#         data = json.loads(request.body)
#         media_id = data.get('media_id')
        
#         if not media_id:
#             print("Missing media_id in the request payload.")
#             return JsonResponse({'error': 'Missing media_id'}, status=400)
        
#         media = Media.objects.filter(id=media_id).first()
#         if not media:
#             print(f"Invalid media_id: {media_id}")
#             return JsonResponse({'error': 'Invalid media_id'}, status=400)

#         Interaction.objects.create(media=media, user=request.user)
#         return JsonResponse({'success': True})

#     except json.JSONDecodeError:
#         print("JSON decode error. Payload may not be valid JSON.")
#         return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
#     except Exception as e:
#         print(f"Error in log_interaction: {e}")
#         return JsonResponse({'error': 'An unexpected error occurred'}, status=400)


# @csrf_exempt
# @require_POST
# def log_interaction(request):
#     try:
#         print(f"Request body: {request.body}")

#         if request.content_type != 'application/json':
#             return JsonResponse({'error': 'Invalid content type'}, status=400)

#         data = json.loads(request.body)
#         media_id = data.get('media_id')

#         if not media_id:
#             print("Missing media_id in the request payload.")
#             return JsonResponse({'error': 'Missing media_id'}, status=400)

#         try:
#             media = Media.objects.get(id=media_id)
#         except Media.DoesNotExist:
#             print(f"Invalid media_id: {media_id}")
#             return JsonResponse({'error': 'Invalid media_id'}, status=400)

#         Interaction.objects.create(media=media, user=request.user, interaction_type='view')
#         return JsonResponse({'success': True})

#     except json.JSONDecodeError:
#         print("JSON decode error. Payload may not be valid JSON.")
#         return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
#     except Exception as e:
#         print(f"Error in log_interaction: {e}")
#         return JsonResponse({'error': 'An unexpected error occurred'}, status=400)


#to search users 
@login_required
def search_users(request, user_id):
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
    paginator = Paginator(users, 100)
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

    # Fetch all media uploads of the media owner (user), excluding private media unless the current user has access
    buddies = Buddy.objects.filter(user=request.user).values_list('buddy', flat=True)
    following_users = request.user.follower_set.all().values_list('following', flat=True)
    user_uploads = Media.objects.filter(user=user).filter(
        Q(is_private=False) | 
        Q(user=request.user) | 
        Q(user__in=buddies) | 
        Q(user__in=following_users)
    ).order_by('-created_at')

    # Paginate the user's uploads
    paginator = Paginator(user_uploads, 12)  # Display 12 uploads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Engagement tracking (view count)
    if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
        media.view_count = F('view_count') + 1
        media.save(update_fields=['view_count'])
        Engagement.objects.create(media=media, user=request.user, engagement_type='view')

    # Making usernames clickable in the description
    description = make_usernames_clickable(media.description)

    # Context for rendering the media detail page
    context = {
        'media': media,
        'description': description,
        'is_following': is_following,
        'is_buddy': is_buddy,  # Passed is_buddy to template
        'has_blocked_media_owner': has_blocked_media_owner,  # Passed for template
        'is_blocked_by_media_owner': is_blocked_by_media_owner,  # Passed for template
        'page_obj': page_obj,  # Paginated user uploads
        'user_uploads': user_uploads,  # All uploads by the user
    }

    return render(request, 'media_detail.html', context)





@login_required
def profile_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(notifications, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'profile_notifications.html', {'page_obj': page_obj})



@login_required
def edit_profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    profile, created = Profile.objects.get_or_create(user=profile_user)

    profile_form = ProfileForm(instance=profile)
    username_form = UsernameUpdateForm(initial={'new_username': profile_user.username})

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

    return render(request, 'edit_profile.html', {
        'form': profile_form,
        'username_form': username_form,
        'profile_user': profile_user
    })


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
        if media.report_count > 500:
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


@login_required
def saved_uploads(request):
    profile = get_object_or_404(Profile, user=request.user)
    saved_media = profile.saved_uploads.all().order_by('-created_at')

    paginator = Paginator(saved_media, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'saved.html', {
        'page_obj': page_obj,
    })


@login_required
def add_story(request):
    if request.method == 'POST':
        file = request.FILES.get('file')
        description = request.POST.get('description')
        
        media = Media.objects.create(
            user=request.user,
            file=file,
            description=description,
            media_type=file.content_type.split('/')[0]
        )
        
        story = Story.objects.create(user=request.user, media=media)
        
        # Redirect to the `view_story` page with the new story's id
        return redirect('user_profile:view_story', story_id=story.id)

    return render(request, 'add_story.html')


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

