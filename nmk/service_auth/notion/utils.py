# user_profile/utils.py
from service_auth.user_profile.models import AuthUser
from django.urls import reverse
import re
from collections import deque
from django.utils.html import escape, mark_safe



def linkify(text):
    url_pattern = re.compile(r'(https?://[^\s]+)')
    return url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)


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


def make_usernames_clickable(content):
    def replace_username(match):
        username = match.group(1)
        try:
            user = AuthUser.objects.get(username=username)
            url = reverse("user_profile:profile", args=[user.id])
            return mark_safe(f'<a href="{url}">@{username}</a>')
        except AuthUser.DoesNotExist:
            return f'@{username}'  # If user does not exist, return the plain text

    content = re.sub(r'@(\w+)', replace_username, content)

    # Then, handle the links
    content = re.sub(r'(https?://\S+)', r'<a href="\1" target="_blank">\1</a>', content)

    return content