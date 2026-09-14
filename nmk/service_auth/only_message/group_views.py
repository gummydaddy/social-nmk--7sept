# nmk/service_auth/only_message/group_views.py

import logging
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User as AuthUser
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse

from . import group_store as store

from django.views.decorators.vary import vary_on_headers
from asgiref.sync import async_to_sync
from django.views.decorators.cache import cache_page, cache_control
from django.views.decorators.cache import never_cache

#user dm counter
from django.db.models import Q, Max
from service_auth.only_message.models import Message
from service_auth.only_message.views import get_dm_conversations_for_user
from service_auth.only_message import dm_unread_store
logger = logging.getLogger(__name__)


def _pic(user):
    try:
        p = user.profile.profile_picture
        return p.url if p else ''
    except Exception:
        return ''


@login_required
def group_list_view(request):
    groups = store.list_user_groups(request.user.id)

    unread_map = store.get_all_unread(request.user.id)

    for g in groups:
        g['unread_count'] = unread_map.get(g['id'], 0)

    my_groups = [g for g in groups if g['kind'] == 'group']
    my_channels = [g for g in groups if g['kind'] == 'broadcast']

    groups_unread_total = sum(g['unread_count'] for g in my_groups)
    channels_unread_total = sum(g['unread_count'] for g in my_channels)

    # ── NEW: DM conversations for the Messages tab ──
    dm_users = get_dm_conversations_for_user(request.user)
    dm_unread_map = dm_unread_store.get_dm_unread_map(request.user.id)
    for u in dm_users:
        u.unread_count = dm_unread_map.get(str(u.id), 0)
    message_unread_total = sum(dm_unread_map.values())

    return render(request, 'only_message/group_list.html', {
        'my_groups': my_groups,
        'my_channels': my_channels,
        'groups_unread_total': groups_unread_total,
        'channels_unread_total': channels_unread_total,
        'dm_users': dm_users,                              # ← NEW
        'message_unread_total': message_unread_total,       # ← NEW
    })


@login_required
@require_POST
def create_group_view(request):
    kind = request.POST.get('kind', 'group')
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    is_public = request.POST.get('is_public') == 'on'
    channel_username = request.POST.get('channel_username', '').strip() if kind == 'broadcast' else None

    if not name:
        messages.error(request, "Please give your group/channel a name.")
        return redirect('only_message:group_list_view')

    group = store.create_group(
        creator_id=request.user.id,
        creator_username=request.user.username,
        creator_pic=_pic(request.user),
        name=name,
        description=description,
        kind=kind,
        is_public=is_public,
        channel_username=channel_username,
    )
    return redirect('only_message:group_chat_view', group_id=group['id'])

'''
@login_required
def group_chat_view(request, group_id):
    group = store.get_group(group_id)
    if not group:
        messages.info(request, "This group/channel no longer exists.")
        return redirect('only_message:group_list_view')

    if not store.is_member(group_id, request.user.id):
        # Public broadcast channels can be previewed/joined; private groups cannot.
        if group['kind'] == 'broadcast' and group['is_public']:
            return render(request, 'only_message/group_preview.html', {'group': group})
        return HttpResponseForbidden("You are not a member of this group.")

    member = store.get_member(group_id, request.user.id)
    return render(request, 'only_message/group_chat.html', {
        'group': group,
        'group_id': group_id,
        'is_admin': store.is_admin(group_id, request.user.id),
        'is_creator': store.is_creator(group_id, request.user.id),
        'my_role': member.get('role') if member else None,
        'can_add_members': store.can_add_members(group_id, request.user.id),   # ← NEW
        'invite_link': f"{request.scheme}://{request.get_host()}/message/invite/{group['invite_code']}/",  # ← NEW

    })
'''

from . import live_store

@login_required
def group_chat_view(request, group_id):
    group = store.get_group(group_id)
    if not group:
        messages.info(request, "This group/channel no longer exists.")
        return redirect('only_message:group_list_view')

    if not store.is_member(group_id, request.user.id):
        if group['kind'] == 'broadcast' and group['is_public']:
            return render(request, 'only_message/group_preview.html', {'group': group})
        return HttpResponseForbidden("You are not a member of this group.")

    member = store.get_member(group_id, request.user.id)

    invite_path = reverse('only_message:invite_landing_view', args=[group['invite_code']])
    invite_link = request.build_absolute_uri(invite_path)

    #new for live option from channels
    active_live_room_id = live_store.get_group_room_id(group_id)
    if active_live_room_id and not live_store.get_room(active_live_room_id):
        active_live_room_id = None   # stale mapping — self-heal
    #new for live option from channels

    return render(request, 'only_message/group_chat.html', {
        'group': group,
        'group_id': group_id,
        'is_admin': store.is_admin(group_id, request.user.id),
        'is_creator': store.is_creator(group_id, request.user.id),
        'my_role': member.get('role') if member else None,
        'can_add_members': store.can_add_members(group_id, request.user.id),
        'invite_link': invite_link,
        'active_live_room_id': active_live_room_id,   # ← NEW

    })

"""
@login_required
def group_unread_counts_api(request):
    '''Fresh unread counts, bypassing any page/browser caching entirely.'''
    groups = store.list_user_groups(request.user.id)
    unread_map = store.get_all_unread(request.user.id)

    counts = {}
    groups_total = 0
    channels_total = 0

    for g in groups:
        c = unread_map.get(g['id'], 0)
        counts[g['id']] = c
        if g['kind'] == 'group':
            groups_total += c
        else:
            channels_total += c

    return JsonResponse({
        'counts': counts,
        'groups_unread_total': groups_total,
        'channels_unread_total': channels_total,
    })
"""

@login_required
def group_unread_counts_api(request):
    """Fresh unread counts, bypassing any page/browser caching entirely."""
    groups = store.list_user_groups(request.user.id)
    unread_map = store.get_all_unread(request.user.id)

    counts = {}
    groups_total = 0
    channels_total = 0

    for g in groups:
        c = unread_map.get(g['id'], 0)
        counts[g['id']] = c
        if g['kind'] == 'group':
            groups_total += c
        else:
            channels_total += c

    return JsonResponse({
        'counts': counts,
        'groups_unread_total': groups_total,
        'channels_unread_total': channels_total,
        'grand_total': groups_total + channels_total,   # ← NEW
    })


'''
@login_required
@require_POST
def join_via_invite_view(request, code):
    group, err = store.join_via_invite(code, request.user.id, request.user.username, _pic(request.user))
    if err:
        messages.error(request, err)
        return redirect('only_message:group_list_view')
    return redirect('only_message:group_chat_view', group_id=group['id'])
'''

'''
@login_required
def invite_landing_view(request, code):
    """
    GET  → show a join confirmation page (this is what fixes the
           'page not found' bug — manually pasted/typed invite links
           are always GET requests, and the old view only accepted POST).
    POST → actually perform the join.
    """
    group = store.get_group_by_invite_code(code)
    if not group:
        messages.error(request, "This invite link is invalid or has expired.")
        return redirect('only_message:group_list_view')

    if store.is_member(group['id'], request.user.id):
        return redirect('only_message:group_chat_view', group_id=group['id'])

    if request.method == 'POST':
        joined_group, err = store.join_via_invite(
            code, request.user.id, request.user.username, _pic(request.user)
        )
        if err:
            messages.error(request, err)
            return redirect('only_message:group_list_view')
        return redirect('only_message:group_chat_view', group_id=joined_group['id'])

    return render(request, 'only_message/invite_landing.html', {
        'group': group,
        'code': code,
    })
'''

@login_required
def invite_landing_view(request, code):
    group = store.get_group_by_invite_code(code)
    if not group:
        messages.error(request, "This invite link is invalid or has expired.")
        return redirect('only_message:group_list_view')

    if store.is_member(group['id'], request.user.id):
        return redirect('only_message:group_chat_view', group_id=group['id'])

    is_private_group = group['kind'] == 'group' and not group.get('is_public')

    if request.method == 'POST':
        if is_private_group:
            messages.error(request, "This is a private group. Ask an admin to add you.")
            return redirect('only_message:group_list_view')

        joined_group, err = store.join_via_invite(
            code, request.user.id, request.user.username, _pic(request.user)
        )
        if err:
            messages.error(request, err)
            return redirect('only_message:group_list_view')
        return redirect('only_message:group_chat_view', group_id=joined_group['id'])

    return render(request, 'only_message/invite_landing.html', {
        'group': group,
        'code': code,
        'is_private_group': is_private_group,
    })


@login_required
@cache_control(public=True, max_age=432000, s_maxage=432050, must_revalidate=True)

def search_channels_view(request):
    query = request.GET.get('q', '').strip()
    results = store.search_public_channels(query, exclude_user_id=request.user.id)
    return render(request, 'only_message/channel_search.html', {
        'query': query,
        'results': results,
    })


@login_required
def search_addable_users_api(request, group_id):
    """
    Username search scoped to a group, used by the 'Add People' box in the
    members panel. Server-side permission check mirrors GroupConsumer's
    _add_member handler exactly — a user who can't add members here gets
    the same 403 whether they try via WS or this endpoint.
    """
    if not store.can_add_members(group_id, request.user.id):
        return JsonResponse({'success': False, 'error': 'You cannot add members here.'}, status=403)

    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'success': True, 'users': []})

    existing_ids = {
        int(m['user_id']) for m in store.list_members(group_id)
        if m['user_id'].isdigit()
    }

    users = (
        AuthUser.objects
        .filter(username__icontains=q)
        .exclude(id__in=existing_ids)
        .exclude(id=request.user.id)[:15]
    )

    return JsonResponse({
        'success': True,
        'users': [{'id': u.id, 'username': u.username, 'pic': _pic(u)} for u in users],
    })

'''
@login_required
@require_POST
def reset_invite_view(request, group_id):
    code, err = store.reset_invite_code(group_id, request.user.id)
    if err:
        return JsonResponse({'success': False, 'error': err}, status=403)
    return JsonResponse({'success': True, 'invite_code': code})
'''

@login_required
@require_POST
def reset_invite_view(request, group_id):
    code, err = store.reset_invite_code(group_id, request.user.id)
    if err:
        return JsonResponse({'success': False, 'error': err}, status=403)
    invite_path = reverse('only_message:invite_landing_view', args=[code])
    return JsonResponse({
        'success': True,
        'invite_code': code,
        'invite_link': request.build_absolute_uri(invite_path),
    })


@login_required
def group_members_api(request, group_id):
    if not store.is_member(group_id, request.user.id):
        return HttpResponseForbidden()
    return JsonResponse({'members': store.list_members(group_id)})


@login_required
@require_POST
def leave_group_view(request, group_id):
    store.leave_group(group_id, request.user.id)
    messages.info(request, "You left the group.")
    return redirect('only_message:group_list_view')


@login_required
@require_POST
def delete_group_view(request, group_id):
    """WhatsApp/Telegram clause: only the creator can permanently delete the group/channel."""
    if not store.is_creator(group_id, request.user.id):
        return HttpResponseForbidden("Only the group creator can delete this group.")
    store.delete_group(group_id)
    messages.success(request, "Group deleted.")
    return redirect('only_message:group_list_view')


@login_required
@require_POST
def mute_group_view(request, group_id):
    muted = request.POST.get('muted') == '1'
    store.mute_group_for_user(group_id, request.user.id, muted)
    return JsonResponse({'success': True, 'muted': muted})





import mimetypes
from django.core.files.storage import default_storage
from django.views.decorators.csrf import csrf_exempt
from .tasks import optimize_image_for_upload


@login_required
@require_POST
def group_file_upload_view(request, group_id):
    """
    Uploads a file for a group/broadcast message and returns its URL.
    Images are optimized synchronously (same helper as 1:1 chat).
    Videos/docs are stored as-is; wire in process_message_file-style
    Celery compression here later if you want it — the message_type
    passed back tells the client which renderer to use meanwhile.
    """
    if not store.is_member(group_id, request.user.id):
        return JsonResponse({'success': False, 'error': 'Not a member'}, status=403)
    if not store.can_send_message(group_id, request.user.id):
        return JsonResponse({'success': False, 'error': 'You cannot post in this group'}, status=403)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)

    MAX_UPLOAD = 25 * 1024 * 1024
    if uploaded_file.size > MAX_UPLOAD:
        return JsonResponse({'success': False, 'error': 'File exceeds 25MB limit'}, status=400)

    content_type = getattr(uploaded_file, 'content_type', '') or mimetypes.guess_type(uploaded_file.name)[0] or ''
    message_type = 'image' if content_type.startswith('image/') else (
        'video' if content_type.startswith('video/') else 'file'
    )

    file_to_store = uploaded_file
    stored_name = f"group_uploads/{group_id}/{uploaded_file.name}"

    if message_type == 'image':
        try:
            processed_content, processed_filename = optimize_image_for_upload(uploaded_file)
            if processed_content is not None:
                file_to_store = processed_content
                stored_name = f"group_uploads/{group_id}/{processed_filename}"
        except Exception as e:
            logger.warning(f"Group image optimization skipped: {e}")

    saved_path = default_storage.save(stored_name, file_to_store)
    file_url = default_storage.url(saved_path)

    return JsonResponse({
        'success': True,
        'file_url': file_url,
        'file_name': uploaded_file.name,
        'message_type': message_type,
    })
