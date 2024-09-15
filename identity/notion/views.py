# your_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Notion, Follow, Comment, Hashtag, Notification, BlockedUser
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from only_card.models import CustomGroupAdmin
from user_profile.utils import make_usernames_clickable
from django.views.decorators.csrf import csrf_protect
import re
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
import random
from collections import deque
from django.core.cache import cache
from django.db.models import Q, Count
from django.views.decorators.csrf import csrf_exempt
from django.utils.html import escape, mark_safe
from django.urls import reverse
# from identity.notion.tasks import send_tagged_user_notifications  # Import the Celery task




AuthUser = get_user_model()

# from user_profile.views import profile 
# from user_profile.models import Story
@login_required
def notion_home(request, notion_id=None):
    user = request.user
    following_users = Follow.objects.filter(follower=user).values_list('following_id', flat=True)

    # Get users with active stories in the last 24 hours
    # active_stories_users = Story.objects.filter(user_id__in=following_users, created_at__gt=timezone.now() - timezone.timedelta(hours=24)).select_related('user', 'user__profile')


    # Get the notions created by users the current user is following
    following_notions = Notion.objects.filter(user__in=following_users)
    # Get the notions created by the current user
    my_notions = Notion.objects.filter(user=user)
    
    
    custom_group_admin_ids = CustomGroupAdmin.objects.filter(user__in=following_users).values_list('user_id', flat=True)
    admin_notions = Notion.objects.filter(user_id__in=custom_group_admin_ids)

    # Combine both querysets
    notions = following_notions | admin_notions | my_notions
    notions = notions.order_by('-created_at')  # Order by creation date

    following_count = Follow.objects.filter(follower=user).count()
    followers_count = Follow.objects.filter(following=user).count()

    context = {
        'notions': notions,
        'user_id': user.id,
        'following_count': following_count,
        'followers_count': followers_count,
        'user': user,
        # 'active_stories_users': active_stories_users,
    }

    if notion_id:
        # notion_id = get_object_or_404(Notion, id=notion_id)
        context['notion_id'] = notion_id

    return render(request, 'notionHome.html', context)


# @login_required
# def post_notion(request):
#     if request.method == 'POST':
#         content = request.POST.get('content', '')

#         # Find all hashtags (#) and tagged usernames (@) in the content
#         hashtags = set(re.findall(r'#(\w+)', content))
#         tagged_usernames = set(re.findall(r'@(\w+)', content))

#         # Process the content to make usernames and links clickable
#         content = make_usernames_clickable(content)  # Ensure this function is defined properly

#         # Set deletion date for the notion (30 days from now)
#         deletion_date = timezone.now() + timedelta(days=1)

#         # Create the notion
#         notion = Notion.objects.create(user=request.user, content=content, deletion_date=deletion_date)

#         # Process and link hashtags to the notion
#         for tag in hashtags:
#             hashtag, created = Hashtag.objects.get_or_create(name=tag)
#             notion.hashtags.add(hashtag)

#         # Process and tag users
#         for username in tagged_usernames:
#             try:
#                 tagged_user = AuthUser.objects.get(username=username)
#                 notion.tagged_users.add(tagged_user)

#                 # Notify the tagged user
#                 Notification.objects.create(
#                     user=tagged_user,
#                     content=f'You were tagged in a notion by {request.user.username}'
#                 )
#             except AuthUser.DoesNotExist:
#                 # If the user does not exist, just continue
#                 pass

#         # Redirect to the notion home page (adjust 'notion_home' URL to your app's URL config)
#         return redirect('notion:notion_home', notion_id=notion.id)

#     # If it's not a POST request, just render the notion posting page
#     return render(request, 'post_notion.html', {'user_id': request.user.id})


# views.py
import logging

@login_required
def post_notion(request):
    if request.method == 'POST':
        content = request.POST.get('content', '')
        logging.info(f"Received content: {content}")

        if not content:
            logging.error("No content provided.")
            return render(request, 'post_notion.html', {'user_id': request.user.id, 'error': 'Content is required.'})

        # Find hashtags and tagged users in the content
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))
        logging.info(f"Found hashtags: {hashtags}")
        logging.info(f"Found tagged users: {tagged_usernames}")

        # Make usernames clickable
        content = make_usernames_clickable(content)

        # Create the notion
        try:
            deletion_date = timezone.now() + timedelta(days=1)
            notion = Notion.objects.create(user=request.user, content=content, deletion_date=deletion_date)
            logging.info(f"Notion created with ID: {notion.id}")
        except Exception as e:
            logging.error(f"Error creating notion: {e}")
            return render(request, 'post_notion.html', {'user_id': request.user.id, 'error': 'Error creating notion.'})

        # Process and add hashtags
        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            notion.hashtags.add(hashtag)

        # Tag users and send notifications
        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                notion.tagged_users.add(tagged_user)
                Notification.objects.create(user=tagged_user, content=f'You were tagged in a notion by {request.user.username}')
            except AuthUser.DoesNotExist:
                pass

        return redirect('notion:notion_home', notion_id=notion.id)

    return render(request, 'post_notion.html', {'user_id': request.user.id})


# @login_required
# def post_notion(request):
#     if request.method == 'POST':
#         content = request.POST.get('content', '')

#         # Extract hashtags and tagged usernames from the content
#         hashtags = set(re.findall(r'#(\w+)', content))
#         tagged_usernames = set(re.findall(r'@(\w+)', content))

#         # Make usernames and links clickable
#         content = make_usernames_clickable(content)

#         # Set deletion date for the notion (30 days from now)
#         deletion_date = timezone.now() + timedelta(days=1)

#         # Create the notion
#         notion = Notion.objects.create(user=request.user, content=content, deletion_date=deletion_date)

#         # Process hashtags
#         for tag in hashtags:
#             hashtag, created = Hashtag.objects.get_or_create(name=tag)
#             notion.hashtags.add(hashtag)

#         # Offload notification sending to a background task using Celery
#         send_tagged_user_notifications.delay(notion.id, list(tagged_usernames), request.user.username)

#         # # Tag users
#         # for username in tagged_usernames:
#         #     try:
#         #         tagged_user = AuthUser.objects.get(username=username)
#         #         notion.tagged_users.add(tagged_user)
#         #         # Notify tagged user
#         #         Notification.objects.create(user=tagged_user, content=f'You were tagged in a notion by {request.user.username}')
#         #     except AuthUser.DoesNotExist:
#         #         pass

#         # Redirect to the notion home page
#         return redirect('notion:notion_home', notion_id=notion.id)

#     # If it's not a POST request, render the notion posting page
#     return render(request, 'post_notion.html', {'user_id': request.user.id})

def following_list(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    following = Follow.objects.filter(follower=profile_user).select_related('following')
    return render(request, 'following_list.html', {'profile_user': profile_user, 'following': following})


@login_required
def followers_list(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    followers = Follow.objects.filter(following=profile_user).select_related('follower')
    return render(request, 'followers_list.html', {'profile_user': profile_user, 'followers': followers})


# @csrf_exempt
# @login_required
# def like_notion(request, notion_id):
#     notion = get_object_or_404(Notion, id=notion_id)
#     like, created = Like.objects.get_or_create(user=request.user, notion=notion)
    
#     if not created:
#         like.delete()
#         liked = False
#     else:
#         Notification.objects.create(
#             user=notion.user,
#             content=f'{request.user.username} liked your notion.',
#             type='like',
#             related_user=request.user,
#             related_notion=notion
#         )
#         liked = True

#     like_count = notion.likes.count()

#     if request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         return JsonResponse({'liked': liked, 'like_count': like_count})

#     return redirect(request.META.get('HTTP_REFERER', 'notion:notion_home'))


@login_required
@csrf_protect
def like_notion(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)
    user = request.user

    if user in notion.likes.all():
        # User has already liked the notion, so unlike it
        notion.likes.remove(user)
        liked = False
    else:
        # User is liking the notion
        notion.likes.add(user)
        Notification.objects.create(
            user=notion.user,
            content=f'{user.username} liked your notion.',
            type='like',
            related_user=user,
            related_notion=notion
        )
        liked = True

    # Return the updated like count and status
    like_count = notion.likes.count()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'like_count': like_count})

    return redirect(request.META.get('HTTP_REFERER', 'notion:notion_home'))


@login_required
def post_comment(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)

    if request.method == 'POST':
        content = request.POST.get('content')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        notion = Notion.objects.get(id=notion_id)

        # Transform content to include clickable usernames
        content = make_usernames_clickable(escape(content))

        # Create the comment associated with the notion
        comment = Comment.objects.create(user=request.user, notion=notion, content=content)

        # Process hashtags
        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        # Process tagged usernames and create notifications
        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{request.user.username} tagged you in a comment: {comment.content}',
                    comment=comment,
                    related_user=request.user,
                    related_notion=notion,
                    type='tag',
                )
            except AuthUser.DoesNotExist:
                pass

        # Create notification for the notion owner
        Notification.objects.create(
            user=notion.user,
            content=f'{request.user.username} commented on your notion.',
            comment=comment,
            type='comment',
            related_user=request.user,
            related_notion=notion
        )

        # Redirect to the notion detail page with a fragment identifier to the new comment
        return redirect(f"{request.build_absolute_uri()}#{comment.id}")

    # If not POST, fallback to redirection to the notion detail page
    return redirect('notion:notion_detail', notion_id=notion.id)





@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    notion = comment.notion
    if request.user == comment.user or request.user == notion.user:
        comment.delete()
        return redirect('notion:notion_detail', notion_id=notion.id)
    return redirect('notion:notion_detail', notion_id=notion.id)


@login_required
def search_users(request):
    query = request.GET.get('q', '')
    
    if query:
        users = (AuthUser.objects.filter(username__icontains=query) | 
                 AuthUser.objects.filter(profile__bio__icontains=query) | 
                 AuthUser.objects.filter(media__description__icontains=query)).distinct()
    else:
        users = AuthUser.objects.none()
    
    followers = Follow.objects.filter(following=request.user)
    following = Follow.objects.filter(follower=request.user)

    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'search_results.html', {
        'page_obj': page_obj,
        'users': users,
        'followers': followers,
        'following': following
    })


@login_required
def my_notions(request, notion_id):
    user = get_object_or_404(AuthUser, id=notion_id)

    # Get the user's notions
    user_notions = Notion.objects.filter(user=user)

    # Get the notions created by CustomGroupAdmins the user is associated with
    custom_group_admin_ids = CustomGroupAdmin.objects.filter(user=user).values_list('user_id', flat=True)
    admin_notions = Notion.objects.filter(user_id__in=custom_group_admin_ids)

    # Combine both querysets
    notions = user_notions | admin_notions
    notions = notions.order_by('-created_at')  # Order by creation date

    following_count = Follow.objects.filter(follower=user).count()
    followers_count = Follow.objects.filter(following=user).count()

    context = {
        'notions': notions,
        'user_id': user.id,
        'following_count': following_count,
        'followers_count': followers_count,
        'user': user
    }

    if notion_id:
        context['notion_id'] = notion_id

    return render(request, 'my_notions.html', context)


@login_required
def notion_detail_view(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)
    related_notions = Notion.objects.filter(user=notion.user).exclude(id=notion_id)

    if request.method == 'POST' and request.is_ajax():
        content = request.POST.get('content')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        comment = Comment.objects.create(user=request.user, notion=notion, content=content)

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
                    related_notion=notion,
                    related_comment=comment
                )
            except AuthUser.DoesNotExist:
                pass

        Notification.objects.create(
            user=notion.user,
            content=f'{request.user.username} commented on your notion.',
            type='comment',
            related_user=request.user,
            related_notion=notion,
            related_comment=comment
        )

        return JsonResponse({
            'status': 'success',
            'username': request.user.username,
            'comment_content': comment.content
        })

    return render(request, 'notion_detail.html', {
        'notion': notion,
        'related_notions': related_notions
    })


# @login_required
# def notifications(request):
#     user = request.user
#     notifications = Notification.objects.filter(user=user).order_by('-created_at')

#     # Process notification content to make usernames and links clickable
#     for notification in notifications:
#         notification.content = make_usernames_clickable(notification.content)
#         if notification.comment:
#             notification.comment.content = make_usernames_clickable(notification.comment.content)
#         if notification.liked_by:
#             notification.liked_by.content = make_usernames_clickable(notification.liked_by.content)

#     return render(request, 'notifications.html', {'notifications': notifications})


@login_required
def notifications(request):
    user = request.user
    # Get current time and the time 8 days ago
    now = timezone.now()
    eight_days_ago = now - timedelta(days=8)
    
    # Filter notifications for the last 8 days and order by creation date
    notifications = Notification.objects.filter(user=user, created_at__gte=eight_days_ago).order_by('-created_at')

    # Process notification content to make usernames and links clickable
    for notification in notifications:
        notification.content = make_usernames_clickable(notification.content)
        if notification.comment:
            notification.comment.content = make_usernames_clickable(notification.comment.content)
        if notification.liked_by:
            notification.liked_by.content = make_usernames_clickable(notification.liked_by.content)

    return render(request, 'notifications.html', {'notifications': notifications})


# @login_required
# def notion_explorer(request):
#     user = request.user

#     # Fetch user's liked notions and extract hashtags
#     liked_notions = Like.objects.filter(user=user).select_related('notion')
#     recent_tags = cache.get(f'{user.id}_recent_tags', deque(maxlen=50))

#     if not recent_tags:
#         recent_tags = deque(maxlen=50)

#     # Update recent_tags queue with hashtags from liked notions
#     for notion in liked_notions:
#         for hashtag in notion.notion.hashtags.all():
#             if hashtag.name not in recent_tags:
#                 recent_tags.append(hashtag.name)

#     # Save updated recent_tags queue to cache
#     cache.set(f'{user.id}_recent_tags', list(recent_tags), None)

#     # Fetch notions based on recent_tags
#     tagged_notions = Notion.objects.filter(hashtags__name__in=recent_tags).distinct()

#     # Fetch newest and most liked notions
#     newest_most_liked_notions = Notion.objects.annotate(like_count=Count('likes')).order_by('-created_at', '-like_count')[:50]

#     # Convert querysets to lists
#     tagged_notions_list = list(tagged_notions)
#     newest_most_liked_notions_list = list(newest_most_liked_notions)

#     # Remove duplicates between the two lists
#     tagged_notions_ids = {notion.id for notion in tagged_notions_list}
#     combined_notions_list = tagged_notions_list + [notion for notion in newest_most_liked_notions_list if notion.id not in tagged_notions_ids]

#     # Randomize within the tagged_notions_list
#     random.shuffle(tagged_notions_list)

#     # Randomize within the rest of the combined list
#     rest_notions_list = [notion for notion in combined_notions_list if notion.id not in tagged_notions_ids]
#     random.shuffle(rest_notions_list)

#     # Combine the lists with priority: tagged_notions_list > newest_most_liked_notions_list > rest_notions_list
#     final_notions_list = tagged_notions_list + rest_notions_list

#     # Search functionality
#     query = request.GET.get('q')
#     if query:
#         search_notions = Notion.objects.filter(
#             Q(content__icontains=query) |
#             Q(user__username__icontains=query) |
#             Q(hashtags__name__icontains=query)
#         ).distinct()
#         final_notions_list = list(search_notions)
#         random.shuffle(final_notions_list)

#     context = {
#         'notions': final_notions_list[:],  # Display up to 50 notions
#     }

#     return render(request, 'notion_explorer.html', context)


@login_required
def notion_explorer(request):
    user = request.user

    # Fetch user's liked notions directly from the Notion model
    liked_notions = Notion.objects.filter(likes=user)  # Fetching notions the user has liked

    # Retrieve recent hashtags from cache or initialize a new deque
    recent_tags = cache.get(f'{user.id}_recent_tags', deque(maxlen=50))
    if not recent_tags:
        recent_tags = deque(maxlen=50)

    # Update recent_tags queue with hashtags from liked notions
    for notion in liked_notions:
        for hashtag in notion.hashtags.all():
            if hashtag.name not in recent_tags:
                recent_tags.append(hashtag.name)

    # Save updated recent_tags queue to cache
    cache.set(f'{user.id}_recent_tags', list(recent_tags), None)

    # Fetch notions based on recent_tags
    tagged_notions = Notion.objects.filter(hashtags__name__in=recent_tags).distinct()

    # Fetch newest and most liked notions
    newest_most_liked_notions = Notion.objects.annotate(like_count=Count('likes')).order_by('-created_at', '-like_count')[:50]

    # Convert querysets to lists
    tagged_notions_list = list(tagged_notions)
    newest_most_liked_notions_list = list(newest_most_liked_notions)

    # Remove duplicates between the two lists
    tagged_notions_ids = {notion.id for notion in tagged_notions_list}
    combined_notions_list = tagged_notions_list + [notion for notion in newest_most_liked_notions_list if notion.id not in tagged_notions_ids]

    # Randomize within the tagged_notions_list
    random.shuffle(tagged_notions_list)

    # Randomize within the rest of the combined list
    rest_notions_list = [notion for notion in combined_notions_list if notion.id not in tagged_notions_ids]
    random.shuffle(rest_notions_list)

    # Combine the lists with priority: tagged_notions_list > newest_most_liked_notions_list > rest_notions_list
    final_notions_list = tagged_notions_list + rest_notions_list

    # Search functionality
    query = request.GET.get('q')
    if query:
        search_notions = Notion.objects.filter(
            Q(content__icontains=query) |
            Q(user__username__icontains(query)) |
            Q(hashtags__name__icontains=query)
        ).distinct()
        final_notions_list = list(search_notions)
        random.shuffle(final_notions_list)

    context = {
        'notions': final_notions_list[:50],  # Display up to 50 notions
    }

    return render(request, 'notion_explorer.html', context)


#block
@login_required
def block_user(request, user_id):
    user_to_block = get_object_or_404(AuthUser, id=user_id)
    BlockedUser.objects.get_or_create(blocker=request.user, blocked=user_to_block)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'blocked'})
    
    return redirect('user_profile:blocked_user_list')

@login_required
def unblock_user(request, user_id):
    user_to_unblock = get_object_or_404(AuthUser, id=user_id)
    blocked_relationship = BlockedUser.objects.filter(blocker=request.user, blocked=user_to_unblock).first()
    
    if blocked_relationship:
        blocked_relationship.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'unblocked'})

    return redirect('user_profile:blocked_user_list')

@login_required
def blocked_user_list(request):
    blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related('blocked')
    return render(request, 'blocked_user_list.html', {'blocked_users': blocked_users})


