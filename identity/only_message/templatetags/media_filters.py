from django import template
import mimetypes

register = template.Library()

@register.filter
def is_image(file_url):
    mime_type, _ = mimetypes.guess_type(file_url)
    return mime_type and mime_type.startswith('image')

@register.filter
def is_video(file_url):
    mime_type, _ = mimetypes.guess_type(file_url)
    return mime_type and mime_type.startswith('video')
