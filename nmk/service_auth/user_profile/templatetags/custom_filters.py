import re
from django import template
from django.contrib.auth.models import User as AuthUser
from service_auth.user_profile.models import Media
from service_auth.user_profile.utils import make_usernames_clickable, linkify


register = template.Library()

# @register.filter(name='is_video')
# def is_video(value):
#     if value:
#         return value.endswith(tuple(('.mp4', '.mov', '.avi', '.mkv')))
#     return False

@register.filter(name='get_hashtags')
def get_hashtags(text):
    return re.findall(r'#(\w+)', text)


@register.filter(name='is_video')
def is_video(file_url):
    return file_url.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))


@register.filter
def is_user(value):
    return isinstance(value, AuthUser)

@register.filter
def is_media(value):
    return isinstance(value, Media)


@register.filter(name='make_clickable')
def make_clickable(value):
    # Apply the username and link functions
    value = make_usernames_clickable(value)
    value = linkify(value)
    return value
