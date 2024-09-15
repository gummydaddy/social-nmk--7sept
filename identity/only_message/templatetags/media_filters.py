from django import template
import mimetypes

register = template.Library()

@register.filter
def is_video(url):
    mime_type, _ = mimetypes.guess_type(url)
    return mime_type and mime_type.startswith('video')

@register.filter
def is_image(url):
    mime_type, _ = mimetypes.guess_type(url)
    return mime_type and mime_type.startswith('image')
