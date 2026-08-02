# nmk/service_auth/only_message/management/commands/cleanup_stale_live_rooms.py
#
# Safety net for the rare case where a host's browser/tab dies without the
# WebSocket disconnect() handler ever firing (e.g. laptop lid closed, app
# force-killed, network dropped before the close frame went out).
#
# The host client pings every 25s and the consumer refreshes a Redis TTL key
# on each ping *from the host*. If that key expires, the room is considered
# abandoned and is torn down here.
#
# Schedule this via Celery Beat (recommended, e.g. every 2 minutes) or cron:
#   python manage.py cleanup_stale_live_rooms

from django.core.management.base import BaseCommand
from service_auth.only_message import live_store as store


class Command(BaseCommand):
    help = "Remove live-stream rooms whose host heartbeat has expired (abandoned streams)."

    def handle(self, *args, **options):
        rooms = store.list_active_rooms(limit=500)
        removed = 0

        for room in rooms:
            room_id = room["room_id"]
            if not store.heartbeat_alive(room_id):
                store.delete_room(room_id)
                removed += 1
                self.stdout.write(f"Removed stale live room: {room_id} (host: {room.get('host_username')})")

        self.stdout.write(self.style.SUCCESS(f"Cleanup complete. Removed {removed} stale live room(s)."))
