# nmk/service_auth/only_message/live_store.py
#
# Redis-backed state for Instagram-Live-style streaming rooms.
# NO new Django models / migrations — everything lives in Redis,
# following the same pattern as call_store.py and stranger_consumer.py.
#
# Key scheme:
#   live:room:{room_id}                     hash  -> room metadata
#   live:room:{room_id}:viewers             hash  -> user_id -> json({username, pic})
#   live:room:{room_id}:costreamers         hash  -> user_id -> json({username, pic})
#   live:room:{room_id}:pending_costream    set   -> user_ids requesting to co-stream
#   live:room:{room_id}:private_allowed     set   -> user_ids allowed into a private room
#   live:room:{room_id}:pending_private     set   -> user_ids requesting private access
#   live:room:{room_id}:chat                list  -> last N chat messages (json), for late joiners
#   live:heartbeat:{room_id}                string with TTL, refreshed by host ping
#   live:active_rooms                        zset -> room_id -> created_at (for ordering)

import json
import time
import uuid
import logging

from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

ACTIVE_ROOMS_KEY = "live:active_rooms"
HEARTBEAT_TTL = 90          # seconds — host must ping at least this often
CHAT_HISTORY_MAX = 30


def _redis():
    return get_redis_connection("default")


def _safe_decode(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _room_key(room_id):
    return f"live:room:{room_id}"


def _viewers_key(room_id):
    return f"live:room:{room_id}:viewers"


def _costreamers_key(room_id):
    return f"live:room:{room_id}:costreamers"


def _pending_costream_key(room_id):
    return f"live:room:{room_id}:pending_costream"


def _private_allowed_key(room_id):
    return f"live:room:{room_id}:private_allowed"


def _pending_private_key(room_id):
    return f"live:room:{room_id}:pending_private"


def _chat_key(room_id):
    return f"live:room:{room_id}:chat"


def _heartbeat_key(room_id):
    return f"live:heartbeat:{room_id}"


# ── add near the other key helpers ──
def _group_live_key(gid):
    return f"group:{gid}:live_room"


def link_group_room(group_id, room_id):
    if group_id:
        _redis().set(_group_live_key(group_id), room_id)


def get_group_room_id(group_id):
    val = _redis().get(_group_live_key(group_id))
    return _safe_decode(val) if val else None


def unlink_group_room(group_id):
    if group_id:
        _redis().delete(_group_live_key(group_id))


# ─────────────────────────────────────────────────────────────────────────────
# Room lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def generate_room_id():
    return uuid.uuid4().hex[:16]

'''
def create_room(room_id, host_id, host_username, host_pic, title, is_private=False):
    r = _redis()
    now = time.time()
    r.hset(_room_key(room_id), mapping={
        "host_id": str(host_id),
        "host_username": host_username or "",
        "host_pic": host_pic or "",
        "title": (title or "").strip()[:120] or f"{host_username}'s live stream",
        "is_private": "1" if is_private else "0",
        "created_at": str(now),
    })
    r.zadd(ACTIVE_ROOMS_KEY, {room_id: now})
    refresh_heartbeat(room_id)
    return get_room(room_id)
'''

def create_room(room_id, host_id, host_username, host_pic, title, is_private=False, linked_group_id=None):
    r = _redis()
    now = time.time()
    r.hset(_room_key(room_id), mapping={
        "host_id": str(host_id),
        "host_username": host_username or "",
        "host_pic": host_pic or "",
        "title": (title or "").strip()[:120] or f"{host_username}'s live stream",
        "is_private": "1" if is_private else "0",
        "created_at": str(now),
        "linked_group_id": linked_group_id or "",   # ← NEW
    })
    r.zadd(ACTIVE_ROOMS_KEY, {room_id: now})
    refresh_heartbeat(room_id)
    if linked_group_id:
        link_group_room(linked_group_id, room_id)    # ← NEW
    return get_room(room_id)

'''
def get_room(room_id):
    r = _redis()
    raw = r.hgetall(_room_key(room_id))
    if not raw:
        return None
    room = {_safe_decode(k): _safe_decode(v) for k, v in raw.items()}
    room["is_private"] = room.get("is_private") == "1"
    room["viewer_count"] = get_viewer_count(room_id)
    room["room_id"] = room_id
    return room
'''

def get_room(room_id):
    r = _redis()
    raw = r.hgetall(_room_key(room_id))
    if not raw:
        return None
    room = {_safe_decode(k): _safe_decode(v) for k, v in raw.items()}
    room["is_private"] = room.get("is_private") == "1"
    room["linked_group_id"] = room.get("linked_group_id") or None   # ← NEW
    room["viewer_count"] = get_viewer_count(room_id)
    room["room_id"] = room_id
    return room

'''
def delete_room(room_id):
    r = _redis()
    keys = [
        _room_key(room_id),
        _viewers_key(room_id),
        _costreamers_key(room_id),
        _pending_costream_key(room_id),
        _private_allowed_key(room_id),
        _pending_private_key(room_id),
        _chat_key(room_id),
        _heartbeat_key(room_id),
    ]
    r.delete(*keys)
    r.zrem(ACTIVE_ROOMS_KEY, room_id)
'''

def delete_room(room_id):
    room = get_room(room_id)   # ← fetch first, need linked_group_id before wiping
    r = _redis()
    keys = [
        _room_key(room_id),
        _viewers_key(room_id),
        _costreamers_key(room_id),
        _pending_costream_key(room_id),
        _private_allowed_key(room_id),
        _pending_private_key(room_id),
        _chat_key(room_id),
        _heartbeat_key(room_id),
    ]
    r.delete(*keys)
    r.zrem(ACTIVE_ROOMS_KEY, room_id)
    if room and room.get("linked_group_id"):
        unlink_group_room(room["linked_group_id"])   # ← NEW


def list_active_rooms(limit=100):
    r = _redis()
    room_ids = r.zrevrange(ACTIVE_ROOMS_KEY, 0, limit - 1)
    rooms = []
    for rid in room_ids:
        rid = _safe_decode(rid)
        room = get_room(rid)
        if room:
            rooms.append(room)
        else:
            # stale entry — clean it up
            r.zrem(ACTIVE_ROOMS_KEY, rid)
    return rooms


def set_privacy(room_id, is_private):
    _redis().hset(_room_key(room_id), "is_private", "1" if is_private else "0")


def refresh_heartbeat(room_id):
    _redis().set(_heartbeat_key(room_id), "1", ex=HEARTBEAT_TTL)


def heartbeat_alive(room_id):
    return _redis().exists(_heartbeat_key(room_id)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Viewers
# ─────────────────────────────────────────────────────────────────────────────

def add_viewer(room_id, user_id, username, pic):
    _redis().hset(_viewers_key(room_id), str(user_id), json.dumps({
        "username": username or "", "pic": pic or "",
    }))


def remove_viewer(room_id, user_id):
    _redis().hdel(_viewers_key(room_id), str(user_id))


def get_viewer_info(room_id, user_id):
    raw = _redis().hget(_viewers_key(room_id), str(user_id))
    if not raw:
        return None
    try:
        return json.loads(_safe_decode(raw))
    except (ValueError, TypeError):
        return None


def get_viewer_count(room_id):
    return _redis().hlen(_viewers_key(room_id))


def list_viewers(room_id):
    raw = _redis().hgetall(_viewers_key(room_id))
    out = []
    for uid, blob in raw.items():
        try:
            info = json.loads(_safe_decode(blob))
        except (ValueError, TypeError):
            info = {}
        out.append({"user_id": _safe_decode(uid), **info})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Co-streamers (approved broadcasters other than the host)
# ─────────────────────────────────────────────────────────────────────────────

def add_costreamer(room_id, user_id, username, pic):
    _redis().hset(_costreamers_key(room_id), str(user_id), json.dumps({
        "username": username or "", "pic": pic or "",
    }))


def remove_costreamer(room_id, user_id):
    _redis().hdel(_costreamers_key(room_id), str(user_id))


def is_costreamer(room_id, user_id):
    return _redis().hexists(_costreamers_key(room_id), str(user_id))


def list_costreamers(room_id):
    """Broadcasting co-streamers only (excludes the host) — used to populate
    the host's viewer-management panel."""
    raw = _redis().hgetall(_costreamers_key(room_id))
    out = []
    for uid, blob in raw.items():
        try:
            info = json.loads(_safe_decode(blob))
        except (ValueError, TypeError):
            info = {}
        out.append({"user_id": _safe_decode(uid), **info})
    return out


def get_broadcasters_info(room_id):
    """
    Returns the full list of active broadcasters for this room:
    the host plus any approved co-streamers. Used to bootstrap a
    newly-joined participant so they know who to request streams from.
    """
    room = get_room(room_id)
    if not room:
        return []

    broadcasters = [{
        "user_id": room["host_id"],
        "username": room["host_username"],
        "pic": room["host_pic"],
        "is_host": True,
    }]

    raw = _redis().hgetall(_costreamers_key(room_id))
    for uid, blob in raw.items():
        try:
            info = json.loads(_safe_decode(blob))
        except (ValueError, TypeError):
            info = {}
        broadcasters.append({
            "user_id": _safe_decode(uid),
            "username": info.get("username", ""),
            "pic": info.get("pic", ""),
            "is_host": False,
        })
    return broadcasters


# ─────────────────────────────────────────────────────────────────────────────
# Join requests (viewer wants to become a co-streamer)
# ─────────────────────────────────────────────────────────────────────────────

def add_pending_costream(room_id, user_id):
    _redis().sadd(_pending_costream_key(room_id), str(user_id))


def remove_pending_costream(room_id, user_id):
    _redis().srem(_pending_costream_key(room_id), str(user_id))


def list_pending_costream(room_id):
    raw = _redis().smembers(_pending_costream_key(room_id))
    return [_safe_decode(x) for x in raw]


# ─────────────────────────────────────────────────────────────────────────────
# Private-room access
# ─────────────────────────────────────────────────────────────────────────────

def grant_private_access(room_id, user_id):
    _redis().sadd(_private_allowed_key(room_id), str(user_id))


def revoke_private_access(room_id, user_id):
    _redis().srem(_private_allowed_key(room_id), str(user_id))


def is_private_allowed(room_id, user_id):
    return _redis().sismember(_private_allowed_key(room_id), str(user_id))


def add_pending_private(room_id, user_id):
    _redis().sadd(_pending_private_key(room_id), str(user_id))


def remove_pending_private(room_id, user_id):
    _redis().srem(_pending_private_key(room_id), str(user_id))


def list_pending_private(room_id):
    raw = _redis().smembers(_pending_private_key(room_id))
    return [_safe_decode(x) for x in raw]


# ─────────────────────────────────────────────────────────────────────────────
# Ephemeral chat history (last N messages, for people who join mid-stream)
# ─────────────────────────────────────────────────────────────────────────────

def push_chat_message(room_id, message_dict):
    r = _redis()
    key = _chat_key(room_id)
    r.rpush(key, json.dumps(message_dict))
    r.ltrim(key, -CHAT_HISTORY_MAX, -1)
    r.expire(key, 60 * 60 * 6)


def get_chat_history(room_id):
    raw = _redis().lrange(_chat_key(room_id), 0, -1)
    out = []
    for blob in raw:
        try:
            out.append(json.loads(_safe_decode(blob)))
        except (ValueError, TypeError):
            continue
    return out
