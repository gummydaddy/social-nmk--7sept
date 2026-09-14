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
'''
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
'''

from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from service_auth.only_message import live_store as store
from service_auth.only_message import group_store


class Command(BaseCommand):
    help = "Remove live-stream rooms whose host heartbeat has expired (abandoned streams)."

    def handle(self, *args, **options):
        rooms = store.list_active_rooms(limit=500)
        removed = 0
        channel_layer = get_channel_layer()

        for room in rooms:
            room_id = room["room_id"]
            if not store.heartbeat_alive(room_id):
                linked_gid = room.get("linked_group_id")
                store.delete_room(room_id)
                removed += 1
                self.stdout.write(f"Removed stale live room: {room_id} (host: {room.get('host_username')})")

                if linked_gid:
                    try:
                        msg = group_store.push_message(
                            linked_gid, sender_id=0, sender_username='', sender_pic='',
                            content='🔴 Live stream ended', message_type='system',
                        )
                        async_to_sync(channel_layer.group_send)(f'group_{linked_gid}', {
                            'type': 'group_message_event', 'message': msg,
                        })
                        async_to_sync(channel_layer.group_send)(f'group_{linked_gid}', {
                            'type': 'live_ended_event',
                        })
                    except Exception as e:
                        self.stdout.write(f"Could not notify group {linked_gid}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Cleanup complete. Removed {removed} stale live room(s)."))
