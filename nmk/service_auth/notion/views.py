# your_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Notion, Follow, Comment, Hashtag, Notification, BlockedUser
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from service_auth.only_card.models import CustomGroupAdmin
from .utils import make_usernames_clickable
from django.views.decorators.csrf import csrf_protect
import re
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
import random
from collections import deque
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.db.models import Q, Count
from django.views.decorators.csrf import csrf_exempt
from django.utils.html import escape, mark_safe
from django.urls import reverse
from .forms import UsernameUpdateForm
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
import logging
from django_redis import get_redis_connection

# from identity.notion.tasks import send_tagged_user_notifications  # Import the Celery task

from django.views.decorators.cache import cache_page, cache_control


AuthUser = get_user_model()

# from user_profile.views import profile 
# from user_profile.models import Story

@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def notion_home(request, notion_id=None):
    user = request.user

    # -------------------------------
    # GUEST / BOT (Anonymous User)
    # -------------------------------

    if not user.is_authenticated:
        notions = (
            Notion.objects
            .select_related('user', 'user__profile')
            #.filter(is_public=True)
            .order_by('-created_at')
        )

        context = {
            'notions': notions,
            'user_id': None,
            'following_count': 0,
            'followers_count': 0,
            'user': None,
        }

        if notion_id:
            context['notion_id'] = notion_id

        return render(request, 'notionHome.html', context)

    # -------------------------------
    # LOGGED-IN USER
    # -------------------------------

    following_users = Follow.objects.filter(follower=user).values_list('following_id', flat=True)

    # Get users with active stories in the last 24 hours
    # active_stories_users = Story.objects.filter(user_id__in=following_users, created_at__gt=timezone.now() - timezone.timedelta(hours=24)).select_related('user', 'user__profile')


    # Get the notions created by users the current user is following
    following_notions = Notion.objects.filter(
        user__in=following_users
    ).exclude(
        user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    ).exclude(
        user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    )

    # Get the notions created by the current user
    my_notions = Notion.objects.filter(user=user)

    # Get custom group admin notions
    custom_group_admin_ids = CustomGroupAdmin.objects.filter(
        user__in=following_users
    ).exclude(
        user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    ).exclude(
        user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    ).values_list('user_id', flat=True)

    admin_notions = Notion.objects.filter(
        user_id__in=custom_group_admin_ids
    ).exclude(
        user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)
    ).exclude(
        user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True)
    )

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

# views.py
import logging
#@login_required
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
            deletion_date = timezone.now() + timedelta(days=28)
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
                # Create a clickable notification to the notion
                Notification.objects.create(
                    user=tagged_user,
                    content=f'You were tagged in a notion by {request.user.username}. <a href="{reverse("notion:notion_detail", args=[notion.id])}">View Notion</a>',
                    related_notion=notion  # Store the notion in the notification
                )
            except AuthUser.DoesNotExist:
                pass

        #return redirect('notion:notion_home', notion_id=notion.id)

        # Instead of redirect → render notion_detail.html
        related_notions = Notion.objects.filter(user=notion.user).exclude(id=notion.id)
        return render(
            request,
            'notion_detail.html',
            {
                'notion': notion,
                'related_notions': related_notions
            }
        )

    return render(request, 'post_notion.html', {'user_id': request.user.id})


#@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def following_list(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    following = Follow.objects.filter(follower=profile_user).select_related('following')
    return render(request, 'following_list.html', {'profile_user': profile_user, 'following': following})


#@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def followers_list(request, user_id):
    profile_user = get_object_or_404(AuthUser, id=user_id)
    followers = Follow.objects.filter(following=profile_user).select_related('follower')
    return render(request, 'followers_list.html', {'profile_user': profile_user, 'followers': followers})


#@login_required
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
            content=f'{user.username} liked your notion. <a href="{reverse("notion:notion_detail", args=[notion.id])}">View Notion</a>',
            type='like',
            related_user=user,
            related_notion=notion  # Store the notion in the notification
        )
        liked = True

    # Return the updated like count and status
    like_count = notion.likes.count()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'like_count': like_count})

    return redirect(request.META.get('HTTP_REFERER', 'notion:notion_home'))


#@login_required
@csrf_protect
def post_comment(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)

    if request.method == 'POST':
        content = request.POST.get('content', '')
        hashtags = set(re.findall(r'#(\w+)', content))
        tagged_usernames = set(re.findall(r'@(\w+)', content))

        # Ensure content is not empty and sanitize it
        content = make_usernames_clickable(escape(content))

        # Create the comment associated with the notion
        comment = Comment.objects.create(user=request.user, notion=notion, content=content)

        # Process hashtags
        for tag in hashtags:
            hashtag, created = Hashtag.objects.get_or_create(name=tag)
            comment.hashtags.add(hashtag)

        # Process tagged usernames and send notifications to tagged users
        for username in tagged_usernames:
            try:
                tagged_user = AuthUser.objects.get(username=username)
                comment.tagged_users.add(tagged_user)

                # Create a clickable notification for the tagged user
                Notification.objects.create(
                    user=tagged_user,
                    content=f'{request.user.username} tagged you in a comment: <a href="{reverse("notion:notion_detail", args=[notion.id])}#{comment.id}">View Comment</a>',
                    comment=comment,
                    related_user=request.user,
                    related_notion=notion,
                    type='tag',
                )
            except AuthUser.DoesNotExist:
                pass

        # Create a notification for the notion owner
        if request.user != notion.user:  # Avoid self-notifications
            Notification.objects.create(
                user=notion.user,
                content=f'{request.user.username} commented on your notion: <a href="{reverse("notion:notion_detail", args=[notion.id])}#{comment.id}">View Comment</a>',
                comment=comment,
                type='comment',
                related_user=request.user,
                related_notion=notion
            )

        # Redirect to the notion detail page with a fragment identifier for the new comment
        #return redirect(f"{reverse('notion:notion_detail', args=[notion.id])}#{comment.id}")

        # Instead of redirecting → render notion_detail.html with updated context
        related_notions = Notion.objects.filter(user=notion.user).exclude(id=notion.id)
        comments = Comment.objects.filter(notion=notion).select_related('user')

        return render(request, 'notion_detail.html', {
            'notion': notion,
            'related_notions': related_notions,
            'comments': comments,
            'new_comment_id': comment.id,  # optionally highlight or scroll to new comment
        })

    # If not a POST request, fallback to redirecting to the notion detail page
    #return redirect('notion:notion_detail', notion_id=notion.id)

    # If not a POST request, render detail page
    related_notions = Notion.objects.filter(user=notion.user).exclude(id=notion.id)
    comments = Comment.objects.filter(notion=notion).select_related('user')

    return render(request, 'notion_detail.html', {
        'notion': notion,
        'related_notions': related_notions,
        'comments': comments,
    })



#@login_required
def delete_notion(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)

    if notion.user == request.user:
        notion.delete()
        return redirect('notion:notion_home')  # or any page you want
    else:
        return HttpResponseForbidden("You are not allowed to delete this notion.")
'''


@login_required
def delete_notion(request, notion_id):
    notion = get_object_or_404(Notion, id=notion_id)

    # --- Permission Checks ---
    is_owner = (notion.user == request.user)

    # Check if current user is a CustomGroupAdmin for the notion's owner
    is_custom_admin = CustomGroupAdmin.objects.filter(
        user=request.user
    ).exists()

    if not (is_owner or is_custom_admin):
        return HttpResponseForbidden("You are not allowed to delete this notion.")

    # --- Delete Notion ---
    user_id = notion.user.id  # The user whose notions page we return to
    notion.delete()

    # Redirect back to the user's notions page
    return redirect('notion:my_notions', notion_id=user_id)
'''


#@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    notion = comment.notion
    if request.user == comment.user or request.user == notion.user:
        comment.delete()
        return redirect('notion:notion_detail', notion_id=notion.id)
    return redirect('notion:notion_detail', notion_id=notion.id)

#works for the search bar at the top of the page 
#@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def search_users(request):
    query = request.GET.get('q', '')
    
    if query:
        users = (AuthUser.objects.filter(username__icontains=query) | 
                #  AuthUser.objects.filter(profile__bio__icontains=query) | 
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
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
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
'''

def my_notions(request, user_id):
    user = get_object_or_404(AuthUser, id=user_id)

    user_notions = Notion.objects.filter(user=user)

    custom_group_admin_ids = CustomGroupAdmin.objects.filter(
        user=user
    ).values_list('user_id', flat=True)

    admin_notions = Notion.objects.filter(user_id__in=custom_group_admin_ids)

    notions = (user_notions | admin_notions).order_by('-created_at')

    following_count = Follow.objects.filter(follower=user).count()
    followers_count = Follow.objects.filter(following=user).count()

    return render(request, 'my_notions.html', {
        'notions': notions,
        'user_id': user.id,
        'following_count': following_count,
        'followers_count': followers_count,
        'user': user
    })
'''

@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
#def notion_detail_view(request, notion_id):
def notion_detail(request, notion_id):
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


#@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
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


#----------------------------------------------------------------
#
#----------------------------------------------------------------

'''
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def notion_explorer(request):
    user = request.user

    # =====================================================
    # GUEST / BOT (NO PERSONALIZATION)
    # =====================================================
    if not user.is_authenticated:
        notions = (
            Notion.objects
            .annotate(like_count=Count('likes'))
            .order_by('-created_at', '-like_count')[:50]
        )

        # Search still allowed
        query = request.GET.get('q')
        if query:
            notions = (
                Notion.objects.filter(
                    Q(content__icontains=query) |
                    Q(user__username__icontains=query) |
                    Q(hashtags__name__icontains=query)
                )
                .distinct()
            )

        return render(request, 'notion_explorer.html', {
            'notions': notions,
            'is_guest': True
        })

    # =====================================================
    # LOGGED-IN USER (PERSONALIZED)
    # =====================================================

    # Fetch user's liked notions directly from the Notion model
    liked_notions = Notion.objects.filter(likes=user)

    # Fetching notions the user has liked
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
    tagged_notions = Notion.objects.filter(
        hashtags__name__in=recent_tags
    ).distinct().filter(
        ~Q(user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)),
        ~Q(user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True))
    )

    # Fetch newest and most liked notions
    newest_most_liked_notions = Notion.objects.annotate(
        like_count=Count('likes')
    ).filter(
        ~Q(user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)),
        ~Q(user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True))
    ).order_by('-created_at', '-like_count')[:50]

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
        Q(user__username__icontains=query) |
        Q(hashtags__name__icontains=query)
    ).filter(
        ~Q(user__in=BlockedUser.objects.filter(blocked=request.user).values_list('blocker', flat=True)),
        ~Q(user__in=BlockedUser.objects.filter(blocker=request.user).values_list('blocked', flat=True))
    ).distinct()
        final_notions_list = list(search_notions)
        random.shuffle(final_notions_list)

    context = {
        'notions': final_notions_list[:50],  # Display up to 50 notions
    }
    return render(request, 'notion_explorer.html', context)
'''



@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def notion_explorer(request):
    user = request.user

    # =====================================================
    # GUEST / BOT (NO PERSONALIZATION)
    # =====================================================
    if not user.is_authenticated:

        query = request.GET.get('q')

        if query:
            notions = (
                Notion.objects.filter(
                    Q(content__icontains=query) |
                    Q(user__username__icontains=query) |
                    Q(hashtags__name__icontains=query)
                )
                .distinct()
            )
        else:
            notions = (
                Notion.objects
                .annotate(like_count=Count('likes'))
                .order_by('-created_at', '-like_count')[:50]
            )

            # Fallback: if no notions found, show randomized notions
            if not notions.exists():
                notions = list(Notion.objects.all())
                random.shuffle(notions)
                notions = notions[:50]

        return render(request, 'notion_explorer.html', {
            'notions': notions,
            'is_guest': True
        })

    # =====================================================
    # LOGGED-IN USER (PERSONALIZED)
    # =====================================================

    # Fetch user's liked notions directly from the Notion model
    liked_notions = Notion.objects.filter(likes=user)

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

    # Blocked users filters
    blocked_by_users = BlockedUser.objects.filter(
        blocked=request.user
    ).values_list('blocker', flat=True)

    blocked_users = BlockedUser.objects.filter(
        blocker=request.user
    ).values_list('blocked', flat=True)

    # Fetch notions based on recent_tags
    tagged_notions = Notion.objects.filter(
        hashtags__name__in=recent_tags
    ).distinct().filter(
        ~Q(user__in=blocked_by_users),
        ~Q(user__in=blocked_users)
    )

    # Fetch newest and most liked notions
    newest_most_liked_notions = Notion.objects.annotate(
        like_count=Count('likes')
    ).filter(
        ~Q(user__in=blocked_by_users),
        ~Q(user__in=blocked_users)
    ).order_by('-created_at', '-like_count')[:50]

    # Convert querysets to lists
    tagged_notions_list = list(tagged_notions)
    newest_most_liked_notions_list = list(newest_most_liked_notions)

    # Remove duplicates
    tagged_notions_ids = {notion.id for notion in tagged_notions_list}

    combined_notions_list = (
        tagged_notions_list +
        [
            notion for notion in newest_most_liked_notions_list
            if notion.id not in tagged_notions_ids
        ]
    )

    # Randomize tagged notions
    random.shuffle(tagged_notions_list)

    # Randomize remaining notions
    rest_notions_list = [
        notion for notion in combined_notions_list
        if notion.id not in tagged_notions_ids
    ]

    random.shuffle(rest_notions_list)

    # Final personalized feed
    final_notions_list = tagged_notions_list + rest_notions_list

    # =====================================================
    # FALLBACK IF NO PERSONALIZED NOTIONS FOUND
    # =====================================================
    if not final_notions_list:

        fallback_notions = list(
            Notion.objects.filter(
                ~Q(user__in=blocked_by_users),
                ~Q(user__in=blocked_users)
            ).distinct()
        )

        random.shuffle(fallback_notions)

        final_notions_list = fallback_notions

    # =====================================================
    # SEARCH FUNCTIONALITY
    # =====================================================
    query = request.GET.get('q')

    if query:
        search_notions = Notion.objects.filter(
            Q(content__icontains=query) |
            Q(user__username__icontains=query) |
            Q(hashtags__name__icontains=query)
        ).filter(
            ~Q(user__in=blocked_by_users),
            ~Q(user__in=blocked_users)
        ).distinct()

        final_notions_list = list(search_notions)
        random.shuffle(final_notions_list)

    context = {
        'notions': final_notions_list[:50],
    }

    return render(request, 'notion_explorer.html', context)

#----------------------------------------------------------------
#
#----------------------------------------------------------------

#block
'''
@login_required
def block_user(request, user_id):
    user_to_block = get_object_or_404(AuthUser, id=user_id)
    BlockedUser.objects.get_or_create(blocker=request.user, blocked=user_to_block)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'blocked'})
    
    return redirect('user_profile:blocked_user_list')
'''

logger = logging.getLogger(__name__)


@login_required
def block_user(request, user_id):
    """
    Block a user and clean up Redis caches
    
    Actions:
    1. Create block relationship
    2. Remove blocked user's media from your recommendations
    3. Clear your seen caches (so you don't see their content)
    4. Remove your view history of their content (for privacy)
    """
    user_to_block = get_object_or_404(AuthUser, id=user_id)
    
    # Prevent self-blocking
    if request.user.id == user_id:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Cannot block yourself'}, status=400)
        return redirect('user_profile:profile', user_id=request.user.id)
    
    # Create block relationship
    blocked_obj, created = BlockedUser.objects.get_or_create(
        blocker=request.user, 
        blocked=user_to_block
    )
    
    # --------------------------------------------------
    # REDIS CACHE CLEANUP
    # --------------------------------------------------
    if created:  # Only do cleanup if this is a new block
        try:
            redis_conn = get_redis_connection("default")
            
            # 1. Remove blocked user's media from your recommendations
            reco_key = f"user:reco:{request.user.id}"
            
            # Get all media IDs from blocked user
            from service_auth.user_profile.models import Media
            blocked_user_media_ids = Media.objects.filter(
                user_id=user_to_block.id
            ).values_list('id', flat=True)[:1000]  # Limit for performance
            
            if blocked_user_media_ids:
                # Remove from recommendations
                redis_conn.zrem(reco_key, *[str(mid) for mid in blocked_user_media_ids])
                logger.info(f"Removed {len(blocked_user_media_ids)} media from recommendations for user {request.user.id}")
            
            # 2. Clear your seen feed caches (so blocked content doesn't pollute your cache)
            seen_feed_pattern = f"user:seen_feed:{request.user.id}"
            try:
                redis_conn.delete(seen_feed_pattern)
                logger.info(f"Cleared seen feed cache for user {request.user.id}")
            except:
                pass
            
            # 3. Clear seen related caches for all media (fresh start)
            seen_related_pattern = f"user:seen_related:{request.user.id}:media:*"
            try:
                # Get all matching keys
                cursor = 0
                while True:
                    cursor, keys = redis_conn.scan(cursor, match=seen_related_pattern, count=100)
                    if keys:
                        redis_conn.delete(*keys)
                    if cursor == 0:
                        break
                logger.info(f"Cleared seen related caches for user {request.user.id}")
            except:
                pass
            
            # 4. Remove blocked user's content from your view history (for privacy)
            user_viewed_key = f"user:viewed:{request.user.id}"
            if blocked_user_media_ids:
                redis_conn.zrem(user_viewed_key, *[str(mid) for mid in blocked_user_media_ids])
            
            # 5. Remove yourself from blocked user's media view tracking (privacy)
            for media_id in blocked_user_media_ids[:100]:  # Limit for performance
                media_viewed_by_key = f"media:viewed_by:{media_id}"
                redis_conn.zrem(media_viewed_by_key, request.user.id)
            
        except Exception as e:
            logger.error(f"Error cleaning Redis on block: {e}")
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'blocked', 'user_id': user_id})
    
    return redirect('user_profile:blocked_user_list')



'''
@login_required
def unblock_user(request, user_id):
    user_to_unblock = get_object_or_404(AuthUser, id=user_id)
    blocked_relationship = BlockedUser.objects.filter(blocker=request.user, blocked=user_to_unblock).first()
    
    if blocked_relationship:
        blocked_relationship.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'unblocked'})

    return redirect('user_profile:blocked_user_list')
'''


@login_required
def unblock_user(request, user_id):
    """
    Unblock a user and optionally restore caches
    
    Actions:
    1. Remove block relationship
    2. Optionally clear seen caches (so you can see their content again)
    """
    user_to_unblock = get_object_or_404(AuthUser, id=user_id)
    blocked_relationship = BlockedUser.objects.filter(
        blocker=request.user, 
        blocked=user_to_unblock
    ).first()
    
    if blocked_relationship:
        blocked_relationship.delete()
        
        # --------------------------------------------------
        # REDIS CACHE CLEANUP (Optional)
        # --------------------------------------------------
        try:
            redis_conn = get_redis_connection("default")
            
            # Clear seen feed cache (so unblocked user's content can appear)
            seen_feed_key = f"user:seen_feed:{request.user.id}"
            redis_conn.delete(seen_feed_key)
            
            # Clear seen related caches (fresh start)
            seen_related_pattern = f"user:seen_related:{request.user.id}:media:*"
            try:
                cursor = 0
                while True:
                    cursor, keys = redis_conn.scan(cursor, match=seen_related_pattern, count=100)
                    if keys:
                        redis_conn.delete(*keys)
                    if cursor == 0:
                        break
            except:
                pass
            
            logger.info(f"Cleared caches for user {request.user.id} after unblocking {user_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning Redis on unblock: {e}")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'action': 'unblocked', 'user_id': user_id})

    return redirect('user_profile:blocked_user_list')




@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def blocked_user_list(request):
    blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related('blocked')
    return render(request, 'blocked_user_list.html', {'blocked_users': blocked_users})


#________________
# function for sitem map
#________________

def notion_detail_map(request, username, notion_id):
    user = get_object_or_404(AuthUser, username=username)
    notion = get_object_or_404(Notion, id=notion_id, user=user)
    return notion_detail_view(request, notion_id=notion.id)  # reuse old view


