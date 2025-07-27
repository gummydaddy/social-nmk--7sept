from django import template
import mimetypes
import os

register = template.Library()

@register.filter
def is_image(file_url):
    mime_type, _ = mimetypes.guess_type(file_url)
    return mime_type and mime_type.startswith('image')

@register.filter
def is_video(file_url):
    mime_type, _ = mimetypes.guess_type(file_url)
    return mime_type and mime_type.startswith('video')


@register.filter
def is_powerpoint(file_url):
    """Check if file is a PowerPoint document"""
    mime_type, _ = mimetypes.guess_type(file_url)
    ppt_types = [
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ]
    return mime_type and mime_type in ppt_types

@register.filter
def is_office_document(file_url):
    """Check if file is any Office document"""
    mime_type, _ = mimetypes.guess_type(file_url)
    office_types = [
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ]
    return mime_type and mime_type in office_types


@register.filter
def ends_with(value, arg):
    """
    Checks if a string ends with the given suffix.
    Usage: {{ some_string|ends_with:".jpg" }}
    """
    if isinstance(value, str):
        return value.lower().endswith(arg.lower())
    return False

@register.filter
def basename(value):
    """
    Returns the base name of a file path (e.g., "document.pdf" from "/media/files/document.pdf").
    Usage: {{ message.file_url|basename }}
    """
    if isinstance(value, str):
        return os.path.basename(value)
    return ""
