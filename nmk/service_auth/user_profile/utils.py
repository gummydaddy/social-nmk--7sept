# user_profile/utils.py
from service_auth.user_profile.models import AuthUser
from django.urls import reverse
import re
from collections import deque
from django.utils.html import escape, mark_safe
from django.contrib.auth import get_user_model
import bleach
from django.db import IntegrityError
from django.http import HttpResponse
from django.template.loader import render_to_string
import base64

# def linkify(text):
#     url_pattern = re.compile(r'(https?://[^\s]+)')
#     return url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)


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
            self.queue.append(hashtag)

    def get_hashtags(self):
        return list(self.queue)

hashtag_queue = HashtagQueue()


def add_to_fifo_list(fifo_list, item, max_length=50):
    if item in fifo_list:
        fifo_list.remove(item)
    fifo_list.append(item)
    if len(fifo_list) > max_length:
        fifo_list.pop(0)
    return fifo_list


#________________________________
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






