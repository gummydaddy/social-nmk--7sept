# nmk/service_auth/only_message/group_consumer.py
#
# WebSocket signaling for Group chats and Broadcast channels.
# Plain channel-group fanout (like LiveConsumer's chat layer) — no WebRTC
# needed here, that's reserved for audio/video calls. All permission
# enforcement (who can send / edit / add members / pin) happens through
# group_store's can_*() checks so a malicious client can't just fake it
# from the frontend.

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from . import group_store as store
from .websocket_notifications import send_notification_sync
from django.urls import reverse

logger = logging.getLogger(__name__)


def _pic(user):
    try:
        p = user.profile.profile_picture
        return p.url if p else ''
    except Exception:
        return ''


class GroupConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        self.gid = self.scope['url_route']['kwargs'].get('group_id')

        if not self.user.is_authenticated or not self.gid:
            await self.close()
            return

        group = await sync_to_async(store.get_group)(self.gid)
        if not group:
            await self.accept()
            await self.send(text_data=json.dumps({'type': 'group_not_found'}))
            await self.close()
            return

        is_member = await sync_to_async(store.is_member)(self.gid, self.user.id)
        if not is_member:
            await self.accept()
            await self.send(text_data=json.dumps({'type': 'not_a_member'}))
            await self.close()
            return

        self.group_name = f'group_{self.gid}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await sync_to_async(store.clear_unread)(self.gid, self.user.id)   # ← THIS LINE — must be present


        recent = await sync_to_async(store.get_messages)(self.gid, limit=50)
        members = await sync_to_async(store.list_members)(self.gid)
        pinned = await sync_to_async(store.list_pinned)(self.gid)
        member = await sync_to_async(store.get_member)(self.gid, self.user.id)

        await self.send(text_data=json.dumps({
            'type': 'group_state',
            'group': group,
            'your_role': member.get('role') if member else None,
            'members': members if group['kind'] == 'group' or await sync_to_async(store.is_admin)(self.gid, self.user.id) else [],
            'member_count': group['member_count'],
            'messages': recent,
            'pinned': pinned,
        }))

        logger.info(f"✅ Group WS connected: {self.user.username} → {self.gid}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return

        t = data.get('type')
        handlers = {
            'send_message':    self._send_message,
            'edit_message':    self._edit_message,
            'delete_message':  self._delete_message,
            'pin_message':     self._pin_message,
            'unpin_message':   self._unpin_message,
            'mark_read':       self._mark_read,
            'typing':          self._typing,
            'view_post':       self._view_post,           # broadcast: track post views
            'add_member':      self._add_member,
            'remove_member':   self._remove_member,
            'set_role':        self._set_role,             # promote/demote
            'update_settings': self._update_settings,       # name/desc/permissions
            'leave_group':     self._leave_group,
            'ping':            self._ping,
        }
        handler = handlers.get(t)
        if handler:
            await handler(data)

    # ══════════════════════════════════════════════════════════════════════
    #  MESSAGING
    # ══════════════════════════════════════════════════════════════════════

    async def _send_message(self, data):
        allowed = await sync_to_async(store.can_send_message)(self.gid, self.user.id)
        if not allowed:
            await self.send(text_data=json.dumps({
                'type': 'error', 'error': 'Only admins can send messages here.'
            }))
            return

        content = (data.get('content') or '').strip()[:4000]
        if not content and not data.get('file_url'):
            return

        pic = await sync_to_async(_pic)(self.user)
        msg = await sync_to_async(store.push_message)(
            self.gid, self.user.id, self.user.username, pic,
            content=content,
            message_type=data.get('message_type', 'text'),
            file_url=data.get('file_url'),
            reply_to=data.get('reply_to'),
        )
        if not msg:
            return

        await sync_to_async(store.increment_unread_for_others)(self.gid, self.user.id)   # ← NEW

        await self.channel_layer.group_send(self.group_name, {
            'type': 'group_message_event',
            'message': msg,
        })

        await self._notify_members(msg)

    async def group_message_event(self, event):
        await self.send(text_data=json.dumps({'type': 'message', 'message': event['message']}))

    
    async def _notify_members(self, msg):
        """Push notification to every OTHER member who hasn't muted this group."""
        group = await sync_to_async(store.get_group)(self.gid)
        members = await sync_to_async(store.list_members)(self.gid)
        preview = msg['content'][:100] if msg['content'] else (
            f"📎 sent an attachment" if msg.get('file_url') else "sent a message"
        )
        group_url = await sync_to_async(reverse)('only_message:group_chat_view', args=[self.gid])

        for m in members:
            uid = int(m['user_id'])
            if uid == self.user.id:
                continue
            muted = await sync_to_async(store.is_muted_for_user)(self.gid, uid)
            if muted:
                continue
            notification_data = {
                'id': f"gmsg_{msg['id']}",
                'type': 'group_message',
                'group_id': self.gid,
                'group_name': group['name'],
                'group_kind': group['kind'],
                'sender': msg['sender_username'],
                'sender_id': msg['sender_id'],
                'message': preview,
                'timestamp': msg['timestamp'],
                'url': group_url,
            }
            await sync_to_async(send_notification_sync)(uid, notification_data)
    

    async def _edit_message(self, data):
        ok, err = await sync_to_async(store.edit_message)(
            self.gid, data.get('message_id'), self.user.id, data.get('content', '')
        )
        if ok:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'message_edited_event',
                'message_id': data.get('message_id'),
                'content': data.get('content', ''),
            })
        else:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))

    async def message_edited_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited', 'message_id': event['message_id'], 'content': event['content'],
        }))

    async def _delete_message(self, data):
        ok, err = await sync_to_async(store.delete_message)(
            self.gid, data.get('message_id'), self.user.id
        )
        if ok:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'message_deleted_event', 'message_id': data.get('message_id'),
            })
        else:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))

    async def message_deleted_event(self, event):
        await self.send(text_data=json.dumps({'type': 'message_deleted', 'message_id': event['message_id']}))

    async def _pin_message(self, data):
        ok, err = await sync_to_async(store.pin_message)(self.gid, self.user.id, data.get('message_id'))
        if ok:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'pin_changed_event', 'message_id': data.get('message_id'), 'pinned': True,
            })
        else:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))

    async def _unpin_message(self, data):
        ok, err = await sync_to_async(store.unpin_message)(self.gid, self.user.id, data.get('message_id'))
        if ok:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'pin_changed_event', 'message_id': data.get('message_id'), 'pinned': False,
            })
        else:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))

    async def pin_changed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'pin_changed', 'message_id': event['message_id'], 'pinned': event['pinned'],
        }))

    async def _view_post(self, data):
        """Broadcast channels: increment view count once per user per post."""
        message_id = data.get('message_id')
        if not message_id:
            return
        await sync_to_async(store.register_view)(self.gid, message_id, self.user.id)
        count = await sync_to_async(store.get_view_count)(self.gid, message_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'view_count_event', 'message_id': message_id, 'count': count,
        })

    async def view_count_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'view_count', 'message_id': event['message_id'], 'count': event['count'],
        }))

    async def _mark_read(self, data):
        await sync_to_async(store.set_last_read)(self.gid, self.user.id, data.get('message_id'))
        await self.channel_layer.group_send(self.group_name, {
            'type': 'read_receipt_event', 'user_id': self.user.id, 'message_id': data.get('message_id'),
        })

    async def read_receipt_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'read_receipt', 'user_id': event['user_id'], 'message_id': event['message_id'],
        }))

    async def _typing(self, data):
        await self.channel_layer.group_send(self.group_name, {
            'type': 'typing_event', 'user_id': self.user.id, 'username': self.user.username,
        })

    async def typing_event(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing', 'user_id': event['user_id'], 'username': event['username'],
            }))

    # ══════════════════════════════════════════════════════════════════════
    #  ADMIN ACTIONS  (all enforced server-side via group_store.can_*/is_admin)
    # ══════════════════════════════════════════════════════════════════════

    async def _add_member(self, data):
        allowed = await sync_to_async(store.can_add_members)(self.gid, self.user.id)
        if not allowed:
            await self.send(text_data=json.dumps({'type': 'error', 'error': 'You cannot add members to this group.'}))
            return

        target_id = data.get('user_id')
        target_username = data.get('username', '')
        target_pic = data.get('pic', '')
        group = await sync_to_async(store.get_group)(self.gid)
        role = 'member' if group['kind'] == 'group' else 'subscriber'

        ok, err = await sync_to_async(store.add_member)(self.gid, target_id, target_username, target_pic, role=role)
        if not ok:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'member_added_event',
            'user_id': target_id, 'username': target_username, 'pic': target_pic, 'role': role,
            'added_by': self.user.username,
        })

        group_url = await sync_to_async(reverse)('only_message:group_chat_view', args=[self.gid])

        await sync_to_async(send_notification_sync)(target_id, {
            'id': f"gadd_{self.gid}",
            'type': 'group_message',
            'group_id': self.gid,
            'group_name': group['name'],
            'group_kind': group['kind'],
            'sender': self.user.username,
            'message': f"{self.user.username} added you to \"{group['name']}\"",
            'timestamp': None,
            'url': group_url,
        })

    async def member_added_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'member_added', 'user_id': event['user_id'], 'username': event['username'],
            'pic': event['pic'], 'role': event['role'], 'added_by': event['added_by'],
        }))

    async def _remove_member(self, data):
        if not await sync_to_async(store.is_admin)(self.gid, self.user.id):
            await self.send(text_data=json.dumps({'type': 'error', 'error': 'Only admins can remove members.'}))
            return

        target_id = str(data.get('user_id'))
        target = await sync_to_async(store.get_member)(self.gid, target_id)
        if target and target.get('role') == 'creator':
            await self.send(text_data=json.dumps({'type': 'error', 'error': 'The group creator cannot be removed.'}))
            return

        await sync_to_async(store.remove_member)(self.gid, target_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'member_removed_event', 'user_id': target_id, 'removed_by': self.user.username,
        })

    async def member_removed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'member_removed', 'user_id': event['user_id'], 'removed_by': event['removed_by'],
        }))
        if str(event['user_id']) == str(self.user.id):
            await self.close()

    async def _set_role(self, data):
        target_id = data.get('user_id')
        role = data.get('role')  # 'admin' | 'member' | 'subscriber'
        ok, err = await sync_to_async(store.set_member_role)(self.gid, self.user.id, target_id, role)
        if not ok:
            await self.send(text_data=json.dumps({'type': 'error', 'error': err}))
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'role_changed_event', 'user_id': target_id, 'role': role, 'changed_by': self.user.username,
        })

    async def role_changed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'role_changed', 'user_id': event['user_id'], 'role': event['role'],
            'changed_by': event['changed_by'],
        }))

    async def _update_settings(self, data):
        allowed = await sync_to_async(store.can_edit_info)(self.gid, self.user.id)
        if not allowed:
            await self.send(text_data=json.dumps({'type': 'error', 'error': 'You cannot edit group info.'}))
            return

        fields = {k: data.get(k) for k in (
            'name', 'description', 'icon_url', 'send_permission',
            'edit_info_permission', 'add_members_permission',
            'allow_comments', 'sign_messages',
            'allow_comments', 'sign_messages', 'is_public',   # ← added is_public
        ) if k in data}

        group = await sync_to_async(store.update_group_settings)(self.gid, **fields)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'settings_changed_event', 'group': group, 'changed_by': self.user.username,
        })

    async def settings_changed_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'settings_changed', 'group': event['group'], 'changed_by': event['changed_by'],
        }))

    async def _leave_group(self, data):
        await sync_to_async(store.leave_group)(self.gid, self.user.id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'member_left_event', 'user_id': self.user.id, 'username': self.user.username,
        })
        await self.close()

    async def member_left_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'member_left', 'user_id': event['user_id'], 'username': event['username'],
        }))

    async def _ping(self, data):
        await self.send(text_data=json.dumps({'type': 'pong'}))



    async def live_started_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'live_started',
            'room_id': event['room_id'],
            'title': event.get('title', ''),
            'started_by': event.get('started_by', ''),
        }))

    async def live_ended_event(self, event):
        await self.send(text_data=json.dumps({'type': 'live_ended'}))
