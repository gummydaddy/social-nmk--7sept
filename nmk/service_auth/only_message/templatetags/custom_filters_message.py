import re
from django import template
from django.utils.safestring import mark_safe
import bleach
from service_auth.user_profile.utils import make_usernames_clickable, linkify


register = template.Library()

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
