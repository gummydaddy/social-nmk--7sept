from django.core.management.base import BaseCommand
from service_auth.user_profile.models import UserHashtagPreference
from service_auth.user_profile.utils import add_to_fifo_list

class Command(BaseCommand):
    help = "Trims hashtag preference lists for all users to their allowed limits."

    def handle(self, *args, **kwargs):
        MAX_LIMITS = {
            "liked_hashtags": 50,
            "not_interested_hashtags": 50,
            "viewed_hashtags": 50,
            "viewed_media": 50,
            "not_interested_media": 50,
            "liked_categories": 10,
            "search_hashtags": 35,
        }

        updated_count = 0
        for pref in UserHashtagPreference.objects.all():
            changed = False

            for field, max_len in MAX_LIMITS.items():
                values = getattr(pref, field, [])
                if len(values) > max_len:
                    trimmed = []
                    for item in values:
                        trimmed = add_to_fifo_list(trimmed, item, max_len)
                    setattr(pref, field, trimmed)
                    changed = True

            if changed:
                pref.save()
                updated_count += 1

        self.stdout.write(f"Trimmed {updated_count} user records.")
