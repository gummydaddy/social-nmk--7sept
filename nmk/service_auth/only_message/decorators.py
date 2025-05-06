from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from notion.models import BlockedUser
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth.decorators import login_required


def user_not_blocked(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        profile_user = kwargs.get('profile_user')  # Assuming profile_user is passed in kwargs or get from URL
        
        # Check if the current user has blocked the profile user
        is_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=profile_user).exists()
        
        # Check if the profile user has blocked the current user
        is_blocked_by_profile_user = BlockedUser.objects.filter(blocker=profile_user, blocked=request.user).exists()
        
        if is_blocked_by_profile_user:
            messages.error(request, 'You are blocked by this user and cannot send messages.')
            return redirect('only_message:message_list_view')

        if is_blocked:
            messages.error(request, 'You have blocked this user and cannot send messages.')
            return redirect('only_message:message_list_view')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
