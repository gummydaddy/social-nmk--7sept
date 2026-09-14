# nmk/service_auth/only_message/live_consumer.py
#
# WebSocket signaling for Instagram-Live-style streaming rooms.
#
# Architecture: mesh fan-out. Every broadcaster (host + approved
# co-streamers) opens one RTCPeerConnection PER OTHER PARTICIPANT
# (viewers and other broadcasters) and pushes its own local stream
# down that connection. This keeps the server as a pure signaling
# relay — no SFU/media server — same philosophy as the existing
# 1:1 audio/video call engine and the stranger-chat consumer.
#
# All room state lives in Redis via live_store.py. No DB models,
# no migrations.

import json
import time
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from . import live_store as store

from . import group_store

logger = logging.getLogger(__name__)


def _pic(user):
    try:
        p = user.profile.profile_picture
        return p.url if p else ''
    except Exception:
        return ''


class LiveConsumer(AsyncWebsocketConsumer):

    # ══════════════════════════════════════════════════════════════════════
    #  CONNECT / DISCONNECT
    # ══════════════════════════════════════════════════════════════════════

    async def connect(self):
        self.user = self.scope["user"]
        self.room_id = self.scope['url_route']['kwargs'].get('room_id')

        if not self.user.is_authenticated or not self.room_id:
            await self.close()
            return

        self.group_name = f'live_{self.room_id}'
        room = await sync_to_async(store.get_room)(self.room_id)

        if not room:
            await self.accept()
            await self.send(text_data=json.dumps({'type': 'room_not_found'}))
            await self.close()
            return

        self.is_host = str(room['host_id']) == str(self.user.id)
        self.role = 'host' if self.is_host else 'viewer'
        self.is_costreamer = False

        if not self.is_host:
            is_co = await sync_to_async(store.is_costreamer)(self.room_id, self.user.id)
            if is_co:
                self.role = 'costreamer'
                self.is_costreamer = True

        # ── Private-room gate ────────────────────────────────────────────
        if room.get('is_private') and self.role == 'viewer':
            allowed = await sync_to_async(store.is_private_allowed)(self.room_id, self.user.id)
            #if not allowed:

            if not allowed and room.get('linked_group_id'):
                # Group-linked live: group membership itself is the grant —
                # no manual per-user approval needed for people already in the group.
                allowed = await sync_to_async(group_store.is_member)(room['linked_group_id'], self.user.id)
            if not allowed:

                self.role = 'pending_private'


        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        pic = await sync_to_async(_pic)(self.user)

        if self.role == 'pending_private':
            await self.send(text_data=json.dumps({
                'type': 'room_state',
                'room_id': self.room_id,
                'host_id': room['host_id'],
                'host_username': room['host_username'],
                'host_pic': room['host_pic'],
                'title': room.get('title', ''),
                'is_private': True,
                'your_role': 'pending_private',
            }))
            logger.info(f"Live WS: {self.user.username} awaiting private access to {self.room_id}")
            return

        await sync_to_async(store.add_viewer)(self.room_id, self.user.id, self.user.username, pic)
        viewer_count = await sync_to_async(store.get_viewer_count)(self.room_id)
        broadcasters = await sync_to_async(store.get_broadcasters_info)(self.room_id)
        chat_history = await sync_to_async(store.get_chat_history)(self.room_id)

        await self.send(text_data=json.dumps({
            'type': 'room_state',
            'room_id': self.room_id,
            'host_id': room['host_id'],
            'host_username': room['host_username'],
            'host_pic': room['host_pic'],
            'title': room.get('title', ''),
            'is_private': room.get('is_private', False),
            'viewer_count': viewer_count,
            'your_role': self.role,
            'your_id': self.user.id,
            'broadcasters': broadcasters,
            'chat_history': chat_history,
        }))

        # Notify everyone else of the viewer-count change (host/costreamer
        # joins are silent here — they're broadcasters, not audience growth)
        if self.role == 'viewer':
            await self.channel_layer.group_send(self.group_name, {
                'type': 'viewer_count_event',
                'viewer_count': viewer_count,
                'event': 'joined',
                'username': self.user.username,
            })

        await self._broadcast_viewer_list()

        logger.info(f"✅ Live WS connected: {self.user.username} role={self.role} room={self.room_id}")

    async def disconnect(self, close_code):
        if not hasattr(self, 'room_id'):
            return

        try:
            if getattr(self, 'is_host', False):
                # Host leaving ends the stream for everyone — no orphaned rooms.
                room = await sync_to_async(store.get_room)(self.room_id)
                linked_gid = room.get('linked_group_id') if room else None

                await sync_to_async(store.delete_room)(self.room_id)
                await self.channel_layer.group_send(self.group_name, {
                    'type': 'stream_ended_event',
                    'reason': 'host_left',
                })

                await self._notify_group_live_ended(linked_gid)   # ← NEW

                logger.info(f"📵 Live room {self.room_id} ended (host left)")
            else:
                if getattr(self, 'is_costreamer', False):
                    await sync_to_async(store.remove_costreamer)(self.room_id, self.user.id)
                    await self.channel_layer.group_send(self.group_name, {
                        'type': 'costreamer_removed_event',
                        'user_id': self.user.id,
                        'reason': 'left',
                    })

                if getattr(self, 'role', None) not in (None, 'pending_private'):
                    await sync_to_async(store.remove_viewer)(self.room_id, self.user.id)
                    await sync_to_async(store.remove_pending_costream)(self.room_id, self.user.id)
                    viewer_count = await sync_to_async(store.get_viewer_count)(self.room_id)
                    await self.channel_layer.group_send(self.group_name, {
                        'type': 'viewer_count_event',
                        'viewer_count': viewer_count,
                        'event': 'left',
                        'username': self.user.username,
                    })

                await self._broadcast_viewer_list()
        except Exception as e:
            logger.error(f"Error in live disconnect: {e}", exc_info=True)
        finally:
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════
    #  INCOMING MESSAGE DISPATCH
    # ══════════════════════════════════════════════════════════════════════

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return

        t = data.get('type')
        handlers = {
            'ready_to_broadcast':      self._ready_to_broadcast,
            'want_stream':             self._want_stream,
            'offer':                   self._relay_offer,
            'answer':                  self._relay_answer,
            'ice_candidate':           self._relay_ice,
            'request_join':            self._request_join,
            'approve_join':            self._approve_join,
            'reject_join':             self._reject_join,
            'remove_viewer':           self._remove_viewer,
            'remove_costreamer':       self._remove_costreamer,
            'end_stream':              self._end_stream,
            'toggle_privacy':          self._toggle_privacy,
            'request_private_access':  self._request_private_access,
            'approve_private_access':  self._approve_private_access,
            'deny_private_access':     self._deny_private_access,
            'chat_message':            self._chat_message,
            'reaction':                self._reaction,
            'mute_costreamer':         self._mute_costreamer,
            'stop_broadcasting':       self._stop_broadcasting,
            'request_viewer_list':     self._request_viewer_list,
            'ping':                    self._ping,
        }
        handler = handlers.get(t)
        if handler:
            await handler(data)

    # ══════════════════════════════════════════════════════════════════════
    #  WEBRTC MESH SIGNALING
    # ══════════════════════════════════════════════════════════════════════

    async def _ready_to_broadcast(self, data):
        """A broadcaster (host or approved co-streamer) has local media ready.
        Tell everyone else in the room so they can request a stream from it."""
        pic = await sync_to_async(_pic)(self.user)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'new_broadcaster_event',
            'broadcaster_id': self.user.id,
            'username': self.user.username,
            'pic': pic,
        })

    async def new_broadcaster_event(self, event):
        if str(event['broadcaster_id']) != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'new_broadcaster',
                'broadcaster_id': event['broadcaster_id'],
                'username': event['username'],
                'pic': event['pic'],
            }))

    async def _stop_broadcasting(self, data):
        """A broadcaster is voluntarily turning off their camera (stays in room)."""
        await self.channel_layer.group_send(self.group_name, {
            'type': 'broadcaster_stopped_event',
            'broadcaster_id': self.user.id,
        })

    async def broadcaster_stopped_event(self, event):
        if str(event['broadcaster_id']) != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'broadcaster_stopped',
                'broadcaster_id': event['broadcaster_id'],
            }))

    async def _want_stream(self, data):
        """A participant wants to receive the given broadcaster's stream —
        relay the request directly to that broadcaster."""
        broadcaster_id = data.get('broadcaster_id')
        if not broadcaster_id:
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'viewer_wants_stream_event',
            'target_id': str(broadcaster_id),
            'viewer_id': self.user.id,
            'viewer_username': self.user.username,
        })

    async def viewer_wants_stream_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'viewer_wants_stream',
                'viewer_id': event['viewer_id'],
                'viewer_username': event['viewer_username'],
            }))

    async def _relay_offer(self, data):
        target_id = data.get('target_id')
        if not target_id:
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'webrtc_offer_event',
            'target_id': str(target_id),
            'from_id': self.user.id,
            'from_username': self.user.username,
            'sdp': data.get('sdp'),
        })

    async def webrtc_offer_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'offer',
                'from_id': event['from_id'],
                'from_username': event['from_username'],
                'sdp': event['sdp'],
            }))

    async def _relay_answer(self, data):
        target_id = data.get('target_id')
        if not target_id:
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'webrtc_answer_event',
            'target_id': str(target_id),
            'from_id': self.user.id,
            'sdp': data.get('sdp'),
        })

    async def webrtc_answer_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'answer',
                'from_id': event['from_id'],
                'sdp': event['sdp'],
            }))

    async def _relay_ice(self, data):
        target_id = data.get('target_id')
        if not target_id:
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'ice_candidate_event',
            'target_id': str(target_id),
            'from_id': self.user.id,
            'candidate': data.get('candidate'),
        })

    async def ice_candidate_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'ice_candidate',
                'from_id': event['from_id'],
                'candidate': event['candidate'],
            }))

    # ══════════════════════════════════════════════════════════════════════
    #  JOIN-AS-CO-STREAMER FLOW
    # ══════════════════════════════════════════════════════════════════════

    async def _request_join(self, data):
        if self.is_host or self.is_costreamer:
            return
        await sync_to_async(store.add_pending_costream)(self.room_id, self.user.id)
        pic = await sync_to_async(_pic)(self.user)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'join_request_event',
            'viewer_id': self.user.id,
            'username': self.user.username,
            'pic': pic,
        })

    async def join_request_event(self, event):
        if self.is_host:
            await self.send(text_data=json.dumps({
                'type': 'join_request',
                'viewer_id': event['viewer_id'],
                'username': event['username'],
                'pic': event['pic'],
            }))

    async def _approve_join(self, data):
        if not self.is_host:
            return
        viewer_id = data.get('viewer_id')
        if not viewer_id:
            return
        info = await sync_to_async(store.get_viewer_info)(self.room_id, viewer_id) or {}
        username = info.get('username', '')
        pic = info.get('pic', '')

        await sync_to_async(store.remove_pending_costream)(self.room_id, viewer_id)
        await sync_to_async(store.add_costreamer)(self.room_id, viewer_id, username, pic)

        await self.channel_layer.group_send(self.group_name, {
            'type': 'join_approved_event',
            'target_id': str(viewer_id),
        })
        await self.channel_layer.group_send(self.group_name, {
            'type': 'costreamer_added_event',
            'user_id': viewer_id,
            'username': username,
            'pic': pic,
        })
        await self._broadcast_viewer_list()

    async def join_approved_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            self.role = 'costreamer'
            self.is_costreamer = True
            await self.send(text_data=json.dumps({'type': 'join_approved'}))

    async def costreamer_added_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'costreamer_added',
            'user_id': event['user_id'],
            'username': event['username'],
            'pic': event['pic'],
        }))

    async def _reject_join(self, data):
        if not self.is_host:
            return
        viewer_id = data.get('viewer_id')
        if not viewer_id:
            return
        await sync_to_async(store.remove_pending_costream)(self.room_id, viewer_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'join_rejected_event',
            'target_id': str(viewer_id),
        })

    async def join_rejected_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({'type': 'join_rejected'}))

    # ══════════════════════════════════════════════════════════════════════
    #  MODERATION
    # ══════════════════════════════════════════════════════════════════════

    async def _remove_viewer(self, data):
        """Host kicks a plain viewer out of the room entirely."""
        if not self.is_host:
            return
        target = data.get('user_id')
        if not target:
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'force_disconnect_event',
            'target_id': str(target),
            'reason': 'removed_by_host',
        })

    async def force_disconnect_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({'type': 'removed', 'reason': event['reason']}))
            await self.close()

    async def _remove_costreamer(self, data):
        """Host demotes a co-streamer back to plain viewer (stays in room,
        stops broadcasting)."""
        if not self.is_host:
            return
        target = data.get('user_id')
        if not target:
            return
        await sync_to_async(store.remove_costreamer)(self.room_id, target)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'costreamer_removed_event',
            'user_id': target,
            'reason': 'removed_by_host',
        })
        await self._broadcast_viewer_list()

    async def costreamer_removed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'costreamer_removed',
            'user_id': event['user_id'],
            'reason': event.get('reason', 'left'),
        }))
        if str(event['user_id']) == str(self.user.id):
            self.role = 'viewer'
            self.is_costreamer = False

    async def _mute_costreamer(self, data):
        """Host asks a co-streamer to mute — enforced client-side."""
        if not self.is_host:
            return
        target = data.get('user_id')
        if not target:
            return
        muted = bool(data.get('muted'))
        await self.channel_layer.group_send(self.group_name, {
            'type': 'mute_costreamer_event',
            'target_id': str(target),
            'muted': muted,
        })

    async def mute_costreamer_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({'type': 'force_mute', 'muted': event['muted']}))


    async def _end_stream(self, data):
        if not self.is_host:
            return

        room = await sync_to_async(store.get_room)(self.room_id)
        linked_gid = room.get('linked_group_id') if room else None

        await sync_to_async(store.delete_room)(self.room_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'stream_ended_event',
            'reason': 'ended_by_host',
        })

        await self._notify_group_live_ended(linked_gid)   # ← NEW

    async def stream_ended_event(self, event):
        await self.send(text_data=json.dumps({'type': 'stream_ended', 'reason': event['reason']}))
        await self.close()

    #new for adding live opition in the channels
    async def _notify_group_live_ended(self, linked_group_id):
        """If this room was tied to a group/channel, tell the group chat
        the live has ended so the topbar badge disappears everywhere, and
        drop a system message into the chat history."""
        if not linked_group_id:
            return
        try:
            msg = await sync_to_async(group_store.push_message)(
                linked_group_id, sender_id=0, sender_username='', sender_pic='',
                content='🔴 Live stream ended', message_type='system',
            )
            await self.channel_layer.group_send(f'group_{linked_group_id}', {
                'type': 'group_message_event', 'message': msg,
            })
            await self.channel_layer.group_send(f'group_{linked_group_id}', {
                'type': 'live_ended_event',
            })
        except Exception as e:
            logger.warning(f"Could not notify group {linked_group_id} of live end: {e}")


    # ══════════════════════════════════════════════════════════════════════
    #  PRIVACY
    # ══════════════════════════════════════════════════════════════════════

    async def _toggle_privacy(self, data):
        if not self.is_host:
            return
        is_private = bool(data.get('is_private'))
        await sync_to_async(store.set_privacy)(self.room_id, is_private)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'privacy_changed_event',
            'is_private': is_private,
        })

    async def privacy_changed_event(self, event):
        await self.send(text_data=json.dumps({'type': 'privacy_changed', 'is_private': event['is_private']}))

    async def _request_private_access(self, data):
        await sync_to_async(store.add_pending_private)(self.room_id, self.user.id)
        pic = await sync_to_async(_pic)(self.user)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'private_access_request_event',
            'viewer_id': self.user.id,
            'username': self.user.username,
            'pic': pic,
        })

    async def private_access_request_event(self, event):
        if self.is_host:
            await self.send(text_data=json.dumps({
                'type': 'private_access_request',
                'viewer_id': event['viewer_id'],
                'username': event['username'],
                'pic': event['pic'],
            }))

    async def _approve_private_access(self, data):
        if not self.is_host:
            return
        viewer_id = data.get('viewer_id')
        if not viewer_id:
            return
        await sync_to_async(store.grant_private_access)(self.room_id, viewer_id)
        await sync_to_async(store.remove_pending_private)(self.room_id, viewer_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'private_access_granted_event',
            'target_id': str(viewer_id),
        })

    async def private_access_granted_event(self, event):
        if str(event['target_id']) != str(self.user.id):
            return

        self.role = 'viewer'
        pic = await sync_to_async(_pic)(self.user)
        await sync_to_async(store.add_viewer)(self.room_id, self.user.id, self.user.username, pic)
        broadcasters = await sync_to_async(store.get_broadcasters_info)(self.room_id)
        viewer_count = await sync_to_async(store.get_viewer_count)(self.room_id)
        chat_history = await sync_to_async(store.get_chat_history)(self.room_id)

        await self.send(text_data=json.dumps({
            'type': 'private_access_granted',
            'broadcasters': broadcasters,
            'viewer_count': viewer_count,
            'chat_history': chat_history,
        }))

        await self.channel_layer.group_send(self.group_name, {
            'type': 'viewer_count_event',
            'viewer_count': viewer_count,
            'event': 'joined',
            'username': self.user.username,
        })
        await self._broadcast_viewer_list()

    async def _deny_private_access(self, data):
        if not self.is_host:
            return
        viewer_id = data.get('viewer_id')
        if not viewer_id:
            return
        await sync_to_async(store.remove_pending_private)(self.room_id, viewer_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'private_access_denied_event',
            'target_id': str(viewer_id),
        })

    async def private_access_denied_event(self, event):
        if str(event['target_id']) == str(self.user.id):
            await self.send(text_data=json.dumps({'type': 'private_access_denied'}))
            await self.close()

    # ══════════════════════════════════════════════════════════════════════
    #  CHAT + REACTIONS
    # ══════════════════════════════════════════════════════════════════════

    async def _chat_message(self, data):
        content = (data.get('content') or '').strip()[:300]
        if not content:
            return
        pic = await sync_to_async(_pic)(self.user)
        msg = {
            'sender': self.user.username,
            'sender_id': self.user.id,
            'sender_pic': pic,
            'content': content,
            'timestamp': time.time(),
        }
        await sync_to_async(store.push_chat_message)(self.room_id, msg)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'chat_message_event',
            **msg,
        })

    async def chat_message_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'sender': event['sender'],
            'sender_id': event['sender_id'],
            'sender_pic': event['sender_pic'],
            'content': event['content'],
            'timestamp': event['timestamp'],
        }))

    async def _reaction(self, data):
        emoji = (data.get('emoji') or '❤️')[:8]
        await self.channel_layer.group_send(self.group_name, {
            'type': 'reaction_event',
            'sender': self.user.username,
            'emoji': emoji,
        })

    async def reaction_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'reaction',
            'sender': event['sender'],
            'emoji': event['emoji'],
        }))

    # ══════════════════════════════════════════════════════════════════════
    #  VIEWER COUNT + HEARTBEAT
    # ══════════════════════════════════════════════════════════════════════

    async def viewer_count_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'viewer_count_update',
            'viewer_count': event['viewer_count'],
            'event': event.get('event'),
            'username': event.get('username'),
        }))

    # ══════════════════════════════════════════════════════════════════════
    #  VIEWER LIST (host's "who's watching / who's co-streaming" panel)
    # ══════════════════════════════════════════════════════════════════════

    async def _broadcast_viewer_list(self):
        """
        Push the current full viewer + co-streamer roster to the room.
        Only the host's socket actually renders it (see viewer_list_event
        below) — everyone else silently ignores it, same pattern used for
        join_request_event and private_access_request_event.
        """
        viewers = await sync_to_async(store.list_viewers)(self.room_id)
        costreamers = await sync_to_async(store.list_costreamers)(self.room_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'viewer_list_event',
            'viewers': viewers,
            'costreamers': costreamers,
        })

    async def viewer_list_event(self, event):
        if self.is_host:
            await self.send(text_data=json.dumps({
                'type': 'viewer_list',
                'viewers': event['viewers'],
                'costreamers': event['costreamers'],
            }))

    async def _request_viewer_list(self, data):
        """Host explicitly asks for a fresh snapshot (e.g. on opening the panel)."""
        if not self.is_host:
            return
        await self._broadcast_viewer_list()

    async def _ping(self, data):
        if self.is_host:
            await sync_to_async(store.refresh_heartbeat)(self.room_id)
        await self.send(text_data=json.dumps({'type': 'pong'}))
