import re
from django import template
from django.utils.safestring import mark_safe
import bleach
from service_auth.user_profile.utils import make_usernames_clickable, linkify

from django.contrib.auth.models import User as AuthUser
from service_auth.user_profile.models import Media
from django.templatetags.static import static  


register = template.Library()

'''
@register.filter(name='make_clickable_message')
def make_clickable_message(value):
    """
    Converts URLs in the text into clickable links.
    """
    url_pattern = re.compile(r'(https?://[^\s]+)')
    linked_text = url_pattern.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', value)
    safe_text = bleach.clean(linked_text, tags=['a'], attributes={'a': ['href', 'target', 'rel']}, strip=True)
    return mark_safe(safe_text)

from django import template
register = template.Library()
register.filter('make_clickable', make_clickable_message)


@register.filter(name='make_clickable')
def make_clickable(value):
    # Apply the username and link functions
    value = make_usernames_clickable(value)
    value = linkify(value)
    return value

'''

#______________________________________________________________________
#enw tem tag to over come contridiction of user name clicking and mesage content clicking 
#______________________________________________________________________
def make_usernames_clickable(text):
    """
    Convert @username into clickable profile links
    """

    username_pattern = re.compile(r'@(\w+)')

    return username_pattern.sub(
        r'<a href="/profile/\1/">@\1</a>',
        text
    )


@register.filter(name='make_clickable')
def make_clickable(value):
    """
    Converts:
    - URLs into clickable links
    - @usernames into clickable links
    """

    if not value:
        return ""

    # Convert URLs
    url_pattern = re.compile(r'(https?://[^\s]+)')

    value = url_pattern.sub(
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        value
    )

    # Convert usernames
    value = make_usernames_clickable(value)

    # Sanitize HTML
    safe_text = bleach.clean(
        value,
        tags=['a'],
        attributes={
            'a': ['href', 'target', 'rel']
        },
        strip=True
    )

    return mark_safe(safe_text)

#______________________________________________________________________
#
#______________________________________________________________________


@register.filter(name='get_hashtags')
def get_hashtags(text):
    return re.findall(r'#(\w+)', text)


@register.filter(name='is_video')
def is_video(file_url):
    return file_url.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))

@register.filter(name='video_mime_type')
def video_mime_type(file_url):
    if is_video(file_url):
        mime_type, _ = mimetypes.guess_type(file_url)
        return mime_type or "video/mp4"
    return ""

@register.filter
def is_user(value):
    return isinstance(value, AuthUser)

@register.filter
def is_media(value):
    return isinstance(value, Media)

@register.filter(name='startswith')
def startswith(text, prefix):
    if not isinstance(text, str):
        return False
    return text.startswith(prefix)


@register.filter
def profile_picture_url(profile):
    if profile and profile.profile_picture and getattr(profile.profile_picture, 'url', None):
        return profile.profile_picture.url
    return static('images/logo.png')
