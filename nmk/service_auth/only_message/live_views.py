# nmk/service_auth/only_message/live_views.py
#
# Views for Instagram-Live-style streaming.
# No new models/migrations — room state lives entirely in Redis
# (see live_store.py). Import these into only_message/urls.py.

import logging

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from . import live_store as store

from . import group_store

logger = logging.getLogger(__name__)


def _profile_pic(user):
    try:
        p = user.profile.profile_picture
        return p.url if p else ''
    except Exception:
        return ''


# ─────────────────────────────────────────────────────────────────────────────
# List of currently-live streams
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def live_list_view(request):
    rooms = store.list_active_rooms()
    return render(request, 'only_message/live_list.html', {'rooms': rooms})


def live_rooms_api(request):
    """JSON polling endpoint the list page uses to refresh without a full reload."""
    rooms = store.list_active_rooms()
    return JsonResponse({'rooms': rooms})


# ─────────────────────────────────────────────────────────────────────────────
# Start a stream
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def start_live_view(request):
    title = request.POST.get('title', '').strip()
    is_private = request.POST.get('is_private') == 'on'

    room_id = store.generate_room_id()
    pic = _profile_pic(request.user)

    store.create_room(
        room_id=room_id,
        host_id=request.user.id,
        host_username=request.user.username,
        host_pic=pic,
        title=title,
        is_private=is_private,
    )

    logger.info(f"🔴 Live room started: {room_id} by {request.user.username}")

    return redirect('only_message:live_room_view', room_id=room_id)


# ─────────────────────────────────────────────────────────────────────────────
# The live room itself (full-page experience)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def live_room_view(request, room_id):
    room = store.get_room(room_id)

    if not room:
        messages.info(request, "This live stream has ended.")
        return redirect('only_message:live_list_view')

    is_host = str(room['host_id']) == str(request.user.id)

    return render(request, 'only_message/live_room.html', {
        'room_id': room_id,
        'room': room,
        'is_host': is_host,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Reliability fallback — end stream via plain HTTP in case the WS
# connection was already severed (e.g. browser killed abruptly).
# Sent via navigator.sendBeacon on page unload.
# ─────────────────────────────────────────────────────────────────────────────
'''
@login_required
@require_POST
def end_live_room_api(request, room_id):
    room = store.get_room(room_id)
    if not room:
        return JsonResponse({'success': True, 'already_ended': True})

    if str(room['host_id']) != str(request.user.id):
        return JsonResponse({'success': False, 'error': 'Only the host can end this stream'}, status=403)

    store.delete_room(room_id)

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f'live_{room_id}', {
            'type': 'stream_ended_event',
            'reason': 'ended_by_host',
        })
    except Exception as e:
        logger.warning(f"Could not broadcast stream_ended for {room_id}: {e}")

    return JsonResponse({'success': True})
'''

@login_required
@require_POST
def end_live_room_api(request, room_id):
    room = store.get_room(room_id)
    if not room:
        return JsonResponse({'success': True, 'already_ended': True})

    if str(room['host_id']) != str(request.user.id):
        return JsonResponse({'success': False, 'error': 'Only the host can end this stream'}, status=403)

    linked_gid = room.get('linked_group_id')
    store.delete_room(room_id)

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f'live_{room_id}', {
            'type': 'stream_ended_event',
            'reason': 'ended_by_host',
        })
        if linked_gid:
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
        logger.warning(f"Could not broadcast stream_ended for {room_id}: {e}")

    return JsonResponse({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
# Start a live tied to a Group or Broadcast Channel
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def start_group_live_view(request, group_id):
    group = group_store.get_group(group_id)
    if not group:
        messages.error(request, "This group/channel no longer exists.")
        return redirect('only_message:group_list_view')

    if not group_store.is_admin(group_id, request.user.id):
        messages.error(request, "Only admins can start a live for this group.")
        return redirect('only_message:group_chat_view', group_id=group_id)

    # If already live, just send them to the existing room instead of
    # spinning up a duplicate.
    existing_room_id = store.get_group_room_id(group_id)
    if existing_room_id and store.get_room(existing_room_id):
        return redirect('only_message:live_room_view', room_id=existing_room_id)

    title = request.POST.get('title', '').strip() or f"{group['name']} Live"
    pic = _profile_pic(request.user)
    room_id = store.generate_room_id()

    store.create_room(
        room_id=room_id,
        host_id=request.user.id,
        host_username=request.user.username,
        host_pic=pic,
        title=title,
        is_private=True,
        linked_group_id=group_id,
    )

    logger.info(f"🔴 Group live started: {room_id} for group {group_id} by {request.user.username}")

    # ── Post a clickable "live" card into the group's message history ──
    msg = group_store.push_message(
        group_id,
        sender_id=request.user.id,
        sender_username=request.user.username,
        sender_pic=pic,
        content=f"{request.user.username} started a live stream",
        message_type='live',
        live_room_id=room_id,
    )
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(f'group_{group_id}', {
        'type': 'group_message_event', 'message': msg,
    })
    async_to_sync(channel_layer.group_send)(f'group_{group_id}', {
        'type': 'live_started_event', 'room_id': room_id,
        'title': title, 'started_by': request.user.username,
    })

    # ── Notify every member (except the host) through the normal pipeline ──
    from .websocket_notifications import send_notification_sync
    from django.urls import reverse
    live_url = reverse('only_message:live_room_view', args=[room_id])

    for m in group_store.list_members(group_id):
        uid = int(m['user_id'])
        if uid == request.user.id:
            continue
        if group_store.is_muted_for_user(group_id, uid):
            continue
        send_notification_sync(uid, {
            'id': f"live_{room_id}",
            'type': 'group_message',
            'group_id': group_id,
            'group_name': group['name'],
            'group_kind': group['kind'],
            'sender': request.user.username,
            'message': f"🔴 {request.user.username} started a live stream",
            'timestamp': None,
            'url': live_url,
        })

    return redirect('only_message:live_room_view', room_id=room_id)
