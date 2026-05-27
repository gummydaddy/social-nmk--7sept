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
            if hashtag in self.queue:
                self.queue.remove(hashtag)
            self.queue.append(hashtag)

    def get_hashtags(self):
        return list(self.queue)

hashtag_queue = HashtagQueue()


'''
def add_to_fifo_list(fifo_list, item, max_length=50):
    if item in fifo_list:
        fifo_list.remove(item)
    fifo_list.append(item)
    if len(fifo_list) > max_length:
        fifo_list.pop(0)
    return fifo_list
'''


def add_to_fifo_list(fifo_list, item, max_length=50):
    """
    Adds an item to a list acting as a FIFO queue, ensuring uniqueness and capped size.
    Safe for Django JSONFields (uses lists, not deque).
    """
    fifo_list = fifo_list or []
    if item in fifo_list:
        fifo_list.remove(item)
    fifo_list.append(item)
    if len(fifo_list) > max_length:
        fifo_list = fifo_list[-max_length:]
    return fifo_list




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




def format_notion_preview_text(content):
    """
    Convert hashtags and mentions into full absolute URLs
    for OpenGraph/Twitter descriptions.
    """
    if not content:
        return ""

    # Replace hashtags (#tag → full link)
    content = re.sub(
        r"#(\w+)",
        lambda m: f"https://socyfie.com/tag/{m.group(1)}",
        content
    )

    # Replace mentions (@user → full link)
    content = re.sub(
        r"@(\w+)",
        lambda m: f"https://socyfie.com/{m.group(1)}",
        content
    )

    return content

