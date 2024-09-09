from django.shortcuts import render, get_object_or_404, redirect
from PIL import Image, ImageFilter, ImageOps
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib import messages
from notion.models import Follow, Notification, Comment, Hashtag, BlockedUser
from django.views.generic import ListView
from .models import Media, Profile, Engagement, AdminNotification, UserHashtagPreference, Story#, Comment
from .forms import MediaForm, ProfileForm, CommentForm
from PIL import Image, ImageFilter, ImageOps
import io
import tempfile
from moviepy.editor import VideoFileClip
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from .serializers import MediaSerializer
from django.views.decorators.http import require_POST
from .utils import linkify, hashtag_queue, add_to_fifo_list, make_usernames_clickable
import re
from django.db.models import F, Count, Q
import random
from collections import deque
from django.template.loader import render_to_string
from django.utils.html import escape, mark_safe
from django.urls import reverse


@login_required
def upload_media(request):
    if request.method == 'POST':
        form = MediaForm(request.POST, request.FILES)
        if form.is_valid():
            media = form.save(commit=False)
            media.user = request.user

            # Process description to make usernames clickable
            media.description = make_usernames_clickable(escape(media.description))

            # Handle image uploads
            if media.file.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                media.media_type = 'image'
                image = Image.open(media.file)
                filter_name = request.POST.get('filter')
                if filter_name:
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

            media.save()
            form.save_m2m()  # Save tags
            return redirect('user_profile:profile', request.user.id)
    else:
        form = MediaForm()
    return render(request, 'upload.html', {'form': form})


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


@login_required
def profile(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
     


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
    

    paginator = Paginator(media, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Check if the current user is following the profile user
    is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()

     # Check if the profile is private and the current user is not following
    if profile_user.profile.is_private and not is_following and request.user != profile_user:
        return render(request, 'profile.html', {
        'profile_user': profile_user,
        # 'page_obj': page_obj,
        'followers_count': followers_count,
        'following_count': following_count,
        'uploads_count': uploads_count,
        'is_following': is_following,
        # 'active_story': active_story,
        'is_blocked': is_blocked,
    })  # Render a page that shows the profile is private
        

    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'page_obj': page_obj,
        'followers_count': followers_count,
        'following_count': following_count,
        'uploads_count': uploads_count,
        'is_following': is_following,
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
def explore(request):
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    viewed_media = user_hashtag_pref.viewed_media

    hashtag_filter = request.GET.get('hashtag', '')

    media_objects = Media.objects.order_by('-created_at')
    if hashtag_filter:
        media_objects = media_objects.filter(hashtags__name__icontains=hashtag_filter)

    media_list = list(media_objects)
    random.shuffle(media_list)

    new_media = [media for media in media_list if media.id not in viewed_media]
    old_media = [media for media in media_list if media.id in viewed_media]

    media_scores = []
    for media in new_media + old_media:
        score = 0
        media_hashtags = [h.name for h in media.hashtags.all()]
        description_hashtags = re.findall(r'#(\w+)', media.description)

        for hashtag in media_hashtags + description_hashtags:
            if hashtag in liked_hashtags:
                score += 1.5
            if hashtag in viewed_hashtags:
                score += 0.9
            if hashtag in not_interested_hashtags:
                score -= 8

        media_scores.append((media, score))

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
        'hashtag_filter': hashtag_filter
    })

# description hashtag search 
@login_required
def search_uploads(request):
    query = request.GET.get('q', '').strip()
    hashtag_filter = request.GET.get('hashtag', '').strip()

    # Fetch user preferences
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    viewed_media = user_hashtag_pref.viewed_media

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

    # Shuffle and score media
    media_list = list(media_objects)
    random.shuffle(media_list)

    media_scores = []
    for media in media_list:
        score = 0
        media_hashtags = [h.name for h in media.hashtags.all()]
        description_hashtags = re.findall(r'#(\w+)', media.description)

        for hashtag in media_hashtags + description_hashtags:
            if hashtag in liked_hashtags:
                score += 1.5
            if hashtag in viewed_hashtags:
                score += 0.9
            if hashtag in not_interested_hashtags:
                score -= 8

        media_scores.append((media, score))

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


@login_required
def explore_detail(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    viewed_media = user_hashtag_pref.viewed_media

    # Update viewed media and hashtags
    if media.id not in viewed_media:
        viewed_media.append(media.id)
        user_hashtag_pref.viewed_media = viewed_media
        user_hashtag_pref.save()

    description_hashtags = re.findall(r'#(\w+)', media.description)
    user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    # Related media logic
    related_media = Media.objects.exclude(id=media_id)
    if liked_hashtags:
        related_media = related_media.annotate(
            num_liked_hashtags=Count(
                'hashtags',
                filter=Q(hashtags__name__in=liked_hashtags)
            )
        ).order_by('-num_liked_hashtags', '?')
    else:
        related_media = related_media.order_by('?')

    # Scoring system
    media_scores = []
    for related in related_media:
        score = 0
        media_hashtags = [h.name for h in related.hashtags.all()]
        description_hashtags = re.findall(r'#(\w+)', related.description)

        for hashtag in media_hashtags + description_hashtags:
            if hashtag in liked_hashtags:
                score += 1.5
            if hashtag in viewed_hashtags:
                score += 0.9
            if hashtag in user_hashtag_pref.not_interested_hashtags:
                score -= 8

        media_scores.append((related, score))

    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    related_media = [m[0] for m in sorted_media][:100]

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
            'description': description
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
        'description': description
    })


@login_required
def following_media(request):
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    not_interested_hashtags = user_hashtag_pref.not_interested_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags

    # Get users that the current user is following
    followed_users = AuthUser.objects.filter(follower_set__follower=request.user)
    
    # Get media from followed users
    media_from_followed_users = Media.objects.filter(user__in=followed_users).exclude(
        engagement__user=request.user, engagement__engagement_type='view'
    ).order_by('-created_at')

    if not media_from_followed_users.exists():
        # If no more media from followed users, use the explore logic
        media = Media.objects.all()

        # Apply hashtag preferences and scoring
        media_list = list(media)
        random.shuffle(media_list)

        media_scores = []
        for m in media_list:
            score = 0
            media_hashtags = [h.name for h in m.hashtags.all()]

            for hashtag in media_hashtags:
                if hashtag in liked_hashtags:
                    score += 1
                if hashtag in not_interested_hashtags:
                    score -= 8
                if hashtag in viewed_hashtags:
                    score += 0.9  # Adjust this weight as needed

            media_scores.append((m, score))

        sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
        sorted_media = [m[0] for m in sorted_media]
    else:
        sorted_media = list(media_from_followed_users)

    # Apply make_usernames_clickable to descriptions
    for media in sorted_media:
        media.description = make_usernames_clickable(media.description)

    paginator = Paginator(sorted_media, 100)
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
# @login_required
# def like_media(request, media_id):
#     media = get_object_or_404(Media, id=media_id)
#     user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

#     if request.user in media.likes.all():
#         media.likes.remove(request.user)
#         liked = False
#     else:
#         media.likes.add(request.user)
#         liked = True

#         # Update the liked hashtags list
#         hashtags_in_description = re.findall(r'#(\w+)', media.description)
#         for hashtag in hashtags_in_description:
#             user_hashtag_pref.liked_hashtags = add_to_fifo_list(user_hashtag_pref.liked_hashtags, hashtag)
        
#         user_hashtag_pref.save()

#         Notification.objects.create(
#             user=media.user,
#             content=f'{request.user.username} liked your media.',
#             type='like',
#             related_user=request.user,
#             related_media=media
#         )

#     if request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         return JsonResponse({'liked': liked, 'like_count': media.likes.count()})

#     return redirect(request.META.get('HTTP_REFERER', 'user_profile:media_detail_view'), media_id=media.id)


@login_required
def like_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

    if request.user in media.likes.all():
        media.likes.remove(request.user)
        liked = False
    else:
        media.likes.add(request.user)
        liked = True

        # Update the liked hashtags list
        hashtags_in_description = re.findall(r'#(\w+)', media.description)
        for hashtag in hashtags_in_description:
            user_hashtag_pref.liked_hashtags = add_to_fifo_list(user_hashtag_pref.liked_hashtags, hashtag)
        
        user_hashtag_pref.save()

        # Create a notification for the media owner
        Notification.objects.create(
            user=media.user,
            content=f'{request.user.username} liked your media.',
            type='like',
            related_user=request.user,
            related_media=media
        )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'like_count': media.likes.count()})

    return redirect(request.META.get('HTTP_REFERER', 'user_profile:media_detail_view'), media_id=media.id)


@login_required
def comment_media(request, media_id):
    media = get_object_or_404(Media, id=media_id)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        # Transform content to include clickable usernames
        content = make_usernames_clickable(escape(content))

        comment = Comment.objects.create(user=request.user, media=media, content=content)

        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{request.user.username} mentioned you in a comment.',
                    type='mention',
                    related_user=request.user,
                    related_media=media,
                    comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        Notification.objects.create(
            user=media.user,
            content=f'{request.user.username} commented on your media.',
            type='comment',
            related_user=request.user,
            related_media=media,
            comment=comment
        )

        # Redirect to the media detail view with the new comment's anchor
        return redirect(f"{request.META.get('HTTP_REFERER', 'user_profile:media_detail_view')}#{comment.id}")

    # If not POST, fallback
    return redirect(request.META.get('HTTP_REFERER', 'user_profile:media_detail_view'), media_id=media.id)



#delete comments
@login_required
def delete_user_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    media = comment.media
    if request.user == comment.user or request.user == media.user:
        comment.delete()
        return redirect('user_profile:media_detail_view', media_id=media.id)
    return redirect('user_profile:media_detail_view', media_id=media.id)

#takes user to the media_detail page 
@login_required
def media_detail_view(request, media_id):
    media = get_object_or_404(Media, id=media_id)

    user = media.user  #new fro private media 

    # Check if the current user is following the media owner
    is_following = Follow.objects.filter(follower=request.user, following=user).exists()

      # Check if the media is private, the user's profile is private, the current user is not a follower, and the current user is not the owner
    if (media.is_private or user.profile.is_private) and not Follow.objects.filter(follower=request.user, following=user).exists() and request.user != user:
        return render(request, 'private_upload.html')  # Show an "upload is private" message

    # User hashtag preference
    user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)
    liked_hashtags = user_hashtag_pref.liked_hashtags
    viewed_hashtags = user_hashtag_pref.viewed_hashtags
    viewed_media = user_hashtag_pref.viewed_media

    # Update viewed media and hashtags
    if media.id not in viewed_media:
        viewed_media.append(media.id)
        user_hashtag_pref.viewed_media = viewed_media
        user_hashtag_pref.save()

    description_hashtags = re.findall(r'#(\w+)', media.description)
    user_hashtag_pref.add_viewed_hashtag(description_hashtags)

    # Related media logic
    related_media_by_user = Media.objects.filter(user=media.user).exclude(id=media_id)
    related_media_by_hashtags = Media.objects.filter(hashtags__name__in=[hashtag.name for hashtag in media.hashtags.all()]).exclude(id=media_id)
    related_media_by_description = Media.objects.filter(description__icontains=' '.join([hashtag.name for hashtag in media.hashtags.all()])).exclude(id=media_id)

    # Combine the three querysets and remove duplicates
    related_media = list(set(list(related_media_by_user) + list(related_media_by_hashtags) + list(related_media_by_description)))

    # Additional filtering and scoring based on user preferences
    if liked_hashtags:
        related_media = Media.objects.filter(id__in=[m.id for m in related_media]).annotate(
            num_liked_hashtags=Count(
                'hashtags',
                filter=Q(hashtags__name__in=liked_hashtags)
            )
        ).order_by('-num_liked_hashtags', '?')
    else:
        related_media = Media.objects.filter(id__in=[m.id for m in related_media]).order_by('?')

    # Scoring system
    media_scores = []
    for related in related_media:
        score = 0
        media_hashtags = [h.name for h in related.hashtags.all()]
        description_hashtags = re.findall(r'#(\w+)', related.description)

        for hashtag in media_hashtags + description_hashtags:
            if hashtag in liked_hashtags:
                score += 1.5
            if hashtag in viewed_hashtags:
                score += 0.9
            if hashtag in user_hashtag_pref.not_interested_hashtags:
                score -= 8

        media_scores.append((related, score))

    sorted_media = sorted(media_scores, key=lambda x: x[1], reverse=True)
    related_media = [m[0] for m in sorted_media][:100]

    # Engagement tracking
    if not Engagement.objects.filter(user=request.user, media=media, engagement_type='view').exists():
        media.view_count = F('view_count') + 1
        media.save(update_fields=['view_count'])
        Engagement.objects.create(media=media, user=request.user, engagement_type='view')

    # Making usernames clickable in the description
    description = make_usernames_clickable(media.description)

    if request.method == 'POST' and request.is_ajax():
        content = request.POST.get('content')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        comment = Comment.objects.create(user=request.user, media=media, content=content)

        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{request.user.username} tagged you in a comment: {comment.content}',
                    type='tag',
                    related_user=request.user,
                    related_media=media,
                    related_comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        Notification.objects.create(
            user=media.user,
            content=f'{request.user.username} commented on your media.',
            type='comment',
            related_user=request.user,
            related_media=media,
            related_comment=comment
        )

        return JsonResponse({
            'status': 'success',
            'username': request.user.username,
            'comment_content': comment.content
        })

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        media_data = {
            'id': media.id,
            'file_url': media.file.url,
            'is_video': media.file.url.endswith('.mp4'),
            'user_username': media.user.username,
            'description': description,
            'is_following': is_following,
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

    paginator = Paginator(related_media, 100)
    page_obj = paginator.get_page(1)
    context = {
        'media': media,
        'page_obj': page_obj,
        'uploads': page_obj,
        'description': description,
        'is_following': is_following,
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

    # Ensure the profile exists, create if not
    profile, created = Profile.objects.get_or_create(user=profile_user)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.bio = linkify(profile.bio) #make link clickable 
            profile.bio = make_usernames_clickable(escape(profile.bio)) #make username clickable 
            profile.save()            
            messages.success(request, 'Profile updated successfully!')
            return redirect('user_profile:profile', user_id=user_id)
        else:
            messages.error(request, 'Error updating your profile')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'edit_profile.html', {'form': form, 'profile_user': profile_user})


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
    Adds hashtags from media description to user's not interested list.

    Args:
    - request (HttpRequest)
    - media_id (int)

    Returns:
    - JsonResponse or HttpResponseRedirect
    """
    try:
        media = get_object_or_404(Media, id=media_id)
        user_hashtag_pref, created = UserHashtagPreference.objects.get_or_create(user=request.user)

        hashtags = re.findall(r'#(\w+)', media.description)
        for hashtag in hashtags:
            user_hashtag_pref.not_interested_hashtags = add_to_fifo_list(user_hashtag_pref.not_interested_hashtags, hashtag)

        user_hashtag_pref.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': 'Hashtags added to not interested list'})

        # Add this return statement
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    except Exception as e:
        # Log the error or return an error response
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

@login_required
def toggle_media_privacy(request, media_id):
    media = get_object_or_404(Media, id=media_id, user=request.user)

    # Toggle the privacy status
    media.is_private = not media.is_private
    media.save()

    # Return the new privacy status as JSON
    return JsonResponse({'is_private': media.is_private})
