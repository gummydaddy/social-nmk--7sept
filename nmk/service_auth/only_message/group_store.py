# nmk/service_auth/only_message/group_store.py
#
# Redis-backed state for Groups (WhatsApp-style) and Broadcast Channels
# (Telegram-style). Same primitive, different `kind` + permission defaults.
# NO new Django models / migrations — follows the live_store.py pattern.
#
# ── Key scheme ──────────────────────────────────────────────────────────────
#   group:{gid}                        hash  -> metadata
#   group:{gid}:members                hash  -> user_id -> json(member)
#   group:{gid}:messages               list  -> json(message)   (capped)
#   group:{gid}:pinned                 list  -> message_id
#   group:{gid}:reads                  hash  -> user_id -> last_read_message_id
#   group:{gid}:views:{message_id}     set   -> user_ids who viewed (broadcast)
#   group:invite:{code}                string -> gid
#   user:groups:{user_id}              set   -> gid  (groups/channels user belongs to)
#   user:group_mute:{user_id}          set   -> gid  (muted notifications)
#
# Roles (members hash "role" field):
#   creator | admin | member            (groups)
#   creator | admin | subscriber        (broadcast channels)

import json
import time
import uuid
import logging

from django_redis import get_redis_connection
from cryptography.fernet import Fernet

from .encryption_utils import encrypt_message, decrypt_message

logger = logging.getLogger(__name__)

MESSAGE_CAP = 2000          # per group/channel — raise if you want deeper history
INVITE_CODE_LEN = 10
MAX_GROUP_MEMBERS = 1024    # WhatsApp's own ceiling
# ── add near the top, with the other key helpers ──
PUBLIC_GROUPS_INDEX_KEY = "group:public_index"


def _sync_public_index(gid, group):
    """Keep the discoverable-channels index in sync with is_public flag."""
    r = _redis()
    if group.get("is_public") and group.get("kind") == "broadcast":
        r.sadd(PUBLIC_GROUPS_INDEX_KEY, gid)
    else:
        r.srem(PUBLIC_GROUPS_INDEX_KEY, gid)

def _redis():
    return get_redis_connection("default")


def _safe_decode(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _gkey(gid):            return f"group:{gid}"
def _members_key(gid):     return f"group:{gid}:members"
def _messages_key(gid):    return f"group:{gid}:messages"
def _pinned_key(gid):      return f"group:{gid}:pinned"
def _reads_key(gid):       return f"group:{gid}:reads"
def _views_key(gid, mid):  return f"group:{gid}:views:{mid}"
def _invite_key(code):     return f"group:invite:{code}"
def _user_groups_key(uid): return f"user:groups:{uid}"
def _user_mute_key(uid):   return f"user:group_mute:{uid}"


# ─────────────────────────────────────────────────────────────────────────────
# CREATE / READ / DELETE
# ─────────────────────────────────────────────────────────────────────────────

def generate_group_id():
    return uuid.uuid4().hex[:16]


def _generate_invite_code():
    return uuid.uuid4().hex[:INVITE_CODE_LEN]


def create_group(creator_id, creator_username, creator_pic, name,
                  description="", icon_url="", kind="group",
                  is_public=False, channel_username=None):
    """
    kind: 'group' (WhatsApp-style) or 'broadcast' (Telegram-style channel)
    """
    r = _redis()
    gid = generate_group_id()
    now = time.time()
    invite_code = _generate_invite_code()

    group_key_material = Fernet.generate_key().decode()  # shared "conversation key"

    r.hset(_gkey(gid), mapping={
        "id": gid,
        "kind": kind,  # 'group' | 'broadcast'
        "name": (name or "").strip()[:150] or ("New Group" if kind == "group" else "New Channel"),
        "description": (description or "").strip()[:500],
        "icon_url": icon_url or "",
        "creator_id": str(creator_id),
        "created_at": str(now),
        "key": group_key_material,
        "invite_code": invite_code,
        "is_public": "1" if is_public else "0",
        "channel_username": (channel_username or "").strip().lower() if kind == "broadcast" else "",

        # ── WhatsApp-style group permission clauses ─────────────────────
        # 'all' = everyone can, 'admins' = admins only
        "send_permission": "all" if kind == "group" else "admins",   # broadcast: only admins post
        "edit_info_permission": "admins",     # who can change name/icon/description
        "add_members_permission": "admins",   # who can add new participants

        # ── Telegram-style broadcast clauses ────────────────────────────
        "allow_comments": "0",   # if enabled, subscribers may reply (discussion group)
        "sign_messages": "0",    # attribute posts to admin username

        "max_members": str(MAX_GROUP_MEMBERS),
    })

    if is_public and channel_username:
        r.set(f"group:username:{channel_username.lower()}", gid)

    r.set(_invite_key(invite_code), gid)

    add_member(gid, creator_id, creator_username, creator_pic, role="creator")

    _sync_public_index(gid, get_group(gid))          # ← ADD THIS LINE

    logger.info(f"Created {kind} {gid} ('{name}') by user {creator_id}")
    return get_group(gid)


def get_group(gid):
    r = _redis()
    raw = r.hgetall(_gkey(gid))
    if not raw:
        return None
    g = {_safe_decode(k): _safe_decode(v) for k, v in raw.items()}
    g["is_public"] = g.get("is_public") == "1"
    g["allow_comments"] = g.get("allow_comments") == "1"
    g["sign_messages"] = g.get("sign_messages") == "1"
    g["member_count"] = member_count(gid)
    g["max_members"] = int(g.get("max_members", MAX_GROUP_MEMBERS))
    return g


def get_group_by_username(channel_username):
    gid = _redis().get(f"group:username:{channel_username.lower()}")
    if not gid:
        return None
    return get_group(_safe_decode(gid))


def update_group_settings(gid, **fields):
    """Caller MUST have already checked can_edit_info() before calling this."""
    allowed = {
        "name", "description", "icon_url", "send_permission",
        "edit_info_permission", "add_members_permission",
        "allow_comments", "sign_messages", "is_public", "channel_username",
    }
    updates = {}
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        if k in ("allow_comments", "sign_messages", "is_public"):
            v = "1" if v else "0"
        updates[k] = str(v)
    if updates:
        _redis().hset(_gkey(gid), mapping=updates)

    group =  get_group(gid)
    if group:
        _sync_public_index(gid, group)                # ← ADD THIS LINE
    return group

def delete_group(gid):
    r = _redis()
    members = list_members(gid)
    for m in members:
        r.srem(_user_groups_key(m["user_id"]), gid)

    group = get_group(gid)
    if group and group.get("invite_code"):
        r.delete(_invite_key(group["invite_code"]))
    if group and group.get("channel_username"):
        r.delete(f"group:username:{group['channel_username']}")

    r.srem(PUBLIC_GROUPS_INDEX_KEY, gid)               # ← ADD THIS LINE

    keys = [_gkey(gid), _members_key(gid), _messages_key(gid),
            _pinned_key(gid), _reads_key(gid)]
    r.delete(*keys)


def list_user_groups(user_id):
    """Groups/channels this user belongs to, most-recently-active-ish (by creation)."""
    r = _redis()
    gids = r.smembers(_user_groups_key(user_id))
    groups = []
    for gid in gids:
        g = get_group(_safe_decode(gid))
        if g:
            groups.append(g)

    def _sort_key(g):
        return float(g.get("last_message_at") or g.get("created_at", 0))

    groups.sort(key=_sort_key, reverse=True)
    return groups

    #groups.sort(key=lambda g: float(g.get("created_at", 0)), reverse=True)
    #return groups


# ─────────────────────────────────────────────────────────────────────────────
# MEMBERSHIP + ROLES
# ─────────────────────────────────────────────────────────────────────────────

def add_member(gid, user_id, username, pic, role="member"):
    r = _redis()
    if member_count(gid) >= MAX_GROUP_MEMBERS:
        return False, "Group is full."

    r.hset(_members_key(gid), str(user_id), json.dumps({
        "user_id": str(user_id),
        "username": username or "",
        "pic": pic or "",
        "role": role,           # creator | admin | member/subscriber
        "joined_at": time.time(),
        "muted_in_group": False,   # per-member notification pref, distinct from user:group_mute
    }))
    r.sadd(_user_groups_key(user_id), gid)
    return True, None


def remove_member(gid, user_id):
    r = _redis()
    r.hdel(_members_key(gid), str(user_id))
    r.hdel(_reads_key(gid), str(user_id))
    r.srem(_user_groups_key(user_id), gid)
    _auto_promote_if_no_admins(gid)


def get_member(gid, user_id):
    raw = _redis().hget(_members_key(gid), str(user_id))
    if not raw:
        return None
    return json.loads(_safe_decode(raw))


def list_members(gid):
    raw = _redis().hgetall(_members_key(gid))
    out = []
    for uid, blob in raw.items():
        try:
            out.append(json.loads(_safe_decode(blob)))
        except (ValueError, TypeError):
            continue
    # creator first, then admins, then everyone else, each alpha by username
    role_order = {"creator": 0, "admin": 1, "member": 2, "subscriber": 2}
    out.sort(key=lambda m: (role_order.get(m.get("role"), 3), m.get("username", "")))
    return out


def member_count(gid):
    return _redis().hlen(_members_key(gid))


def is_member(gid, user_id):
    return _redis().hexists(_members_key(gid), str(user_id))


def is_admin(gid, user_id):
    m = get_member(gid, user_id)
    return bool(m and m.get("role") in ("creator", "admin"))


def is_creator(gid, user_id):
    m = get_member(gid, user_id)
    return bool(m and m.get("role") == "creator")


def set_member_role(gid, actor_id, target_id, role):
    """
    WhatsApp clause: only admins can promote/demote.
    The creator can never be demoted by anyone but themself leaving the group
    (ownership transfer is handled separately, not via role change).
    """
    if not is_admin(gid, actor_id):
        return False, "Only admins can change roles."

    target = get_member(gid, target_id)
    if not target:
        return False, "User is not a member."
    if target.get("role") == "creator":
        return False, "The group creator's role cannot be changed."
    if role not in ("admin", "member", "subscriber"):
        return False, "Invalid role."

    target["role"] = role
    _redis().hset(_members_key(gid), str(target_id), json.dumps(target))
    return True, None


def _auto_promote_if_no_admins(gid):
    """
    WhatsApp clause: a group must always have at least one admin. If the last
    admin leaves/is removed, auto-promote the longest-standing remaining
    member so the group is never orphaned.
    """
    members = list_members(gid)
    if not members:
        return
    if any(m.get("role") in ("creator", "admin") for m in members):
        return
    oldest = min(members, key=lambda m: m.get("joined_at", time.time()))
    oldest["role"] = "admin"
    _redis().hset(_members_key(gid), oldest["user_id"], json.dumps(oldest))
    logger.info(f"Auto-promoted {oldest['user_id']} to admin in group {gid} (no admins left)")


def leave_group(gid, user_id):
    """
    WhatsApp clause: if the CREATOR leaves, ownership transfers to the
    longest-standing admin (or longest-standing member if none) before
    the creator is removed, so the group is never without an owner.
    """
    member = get_member(gid, user_id)
    if not member:
        return
    if member.get("role") == "creator":
        members = [m for m in list_members(gid) if m["user_id"] != str(user_id)]
        if members:
            admins = [m for m in members if m.get("role") == "admin"]
            successor = min(admins or members, key=lambda m: m.get("joined_at", time.time()))
            successor["role"] = "creator"
            _redis().hset(_members_key(gid), successor["user_id"], json.dumps(successor))
            logger.info(f"Ownership of group {gid} transferred to {successor['user_id']}")
    remove_member(gid, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSION CHECKS (WhatsApp/Telegram clauses)
# ─────────────────────────────────────────────────────────────────────────────

def can_send_message(gid, user_id):
    group = get_group(gid)
    if not group or not is_member(gid, user_id):
        return False
    if group["send_permission"] == "all":
        return True
    return is_admin(gid, user_id)


def can_edit_info(gid, user_id):
    group = get_group(gid)
    if not group or not is_member(gid, user_id):
        return False
    if group["edit_info_permission"] == "all":
        return True
    return is_admin(gid, user_id)


def can_add_members(gid, user_id):
    group = get_group(gid)
    if not group or not is_member(gid, user_id):
        return False
    if group["add_members_permission"] == "all":
        return True
    return is_admin(gid, user_id)


def can_comment(gid, user_id):
    """Broadcast channels: subscribers can only reply if allow_comments is on."""
    group = get_group(gid)
    if not group:
        return False
    if group["kind"] != "broadcast":
        return can_send_message(gid, user_id)
    if is_admin(gid, user_id):
        return True
    return group.get("allow_comments") and is_member(gid, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# INVITE LINKS
# ─────────────────────────────────────────────────────────────────────────────

def reset_invite_code(gid, actor_id):
    """WhatsApp/Telegram clause: only admins can revoke/regenerate the invite link."""
    if not is_admin(gid, actor_id):
        return None, "Only admins can reset the invite link."
    r = _redis()
    group = get_group(gid)
    if group and group.get("invite_code"):
        r.delete(_invite_key(group["invite_code"]))
    new_code = _generate_invite_code()
    r.hset(_gkey(gid), "invite_code", new_code)
    r.set(_invite_key(new_code), gid)
    return new_code, None

'''
def join_via_invite(code, user_id, username, pic):
    gid = _redis().get(_invite_key(code))
    if not gid:
        return None, "This invite link is invalid or has expired."
    gid = _safe_decode(gid)
    group = get_group(gid)
    if not group:
        return None, "This group no longer exists."
    if is_member(gid, user_id):
        return group, None
    role = "member" if group["kind"] == "group" else "subscriber"
    ok, err = add_member(gid, user_id, username, pic, role=role)
    if not ok:
        return None, err
    return group, None
'''

def join_via_invite(code, user_id, username, pic):
    gid = _redis().get(_invite_key(code))
    if not gid:
        return None, "This invite link is invalid or has expired."
    gid = _safe_decode(gid)
    group = get_group(gid)
    if not group:
        return None, "This group no longer exists."
    if is_member(gid, user_id):
        return group, None

    # WhatsApp clause: private GROUPS cannot be self-joined via invite link —
    # only an admin can add members. Broadcast channels are exempt: Telegram
    # private channels are still joinable via invite link (only *public*
    # channels are additionally discoverable by @username search).
    if group["kind"] == "group" and not group.get("is_public"):
        return None, "This is a private group. Ask an admin to add you as a member."

    role = "member" if group["kind"] == "group" else "subscriber"
    ok, err = add_member(gid, user_id, username, pic, role=role)
    if not ok:
        return None, err
    return group, None

# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

def push_message(gid, sender_id, sender_username, sender_pic, content,
                  message_type="text", file_url=None, reply_to=None, live_room_id=None):
    r = _redis()
    group = get_group(gid)
    if not group:
        return None

    message_id = uuid.uuid4().hex[:12]
    now = time.time()

    encrypted_content = None
    if content:
        try:
            encrypted_content = encrypt_message(content, group["key"].encode())
        except Exception as e:
            logger.warning(f"Group message encryption failed, storing plaintext: {e}")

    msg = {
        "id": message_id,
        "gid": gid,
        "sender_id": str(sender_id),
        "sender_username": sender_username,
        "sender_pic": sender_pic or "",
        "content": encrypted_content or "",
        "message_type": message_type,   # text | image | video | file | system
        "file_url": file_url,

        "live_room_id": live_room_id,        # ← NEW

        "reply_to": reply_to,
        "timestamp": now,
        "edited": False,
        "deleted": False,
    }

    r.rpush(_messages_key(gid), json.dumps(msg))
    r.ltrim(_messages_key(gid), -MESSAGE_CAP, -1)
    r.hset(_gkey(gid), "last_message_at", str(now))   # ← NEW: drives recency sort

    # Return a plaintext copy for immediate WS broadcast (client never needs
    # to decrypt live traffic — same pattern as 1:1 chat).
    out = dict(msg)
    out["content"] = content
    return out


def get_messages(gid, before_id=None, limit=50):
    """Paginate backward through history; returns oldest→newest for the page."""
    r = _redis()
    group = get_group(gid)
    if not group:
        return []

    raw_all = r.lrange(_messages_key(gid), 0, -1)
    parsed = []
    for raw in raw_all:
        try:
            parsed.append(json.loads(_safe_decode(raw)))
        except (ValueError, TypeError):
            continue

    if before_id:
        idx = next((i for i, m in enumerate(parsed) if m["id"] == before_id), None)
        parsed = parsed[:idx] if idx is not None else parsed

    page = parsed[-limit:]

    key = group["key"].encode()
    for m in page:
        if m.get("content"):
            m["content"] = decrypt_message(m["content"], key) or "[Decryption Failed]"

    return page


def edit_message(gid, message_id, actor_id, new_content):
    """WhatsApp clause: only the original sender may edit their own message."""
    r = _redis()
    raw_all = r.lrange(_messages_key(gid), 0, -1)
    group = get_group(gid)
    if not group:
        return False, "Group not found."

    for i, raw in enumerate(raw_all):
        m = json.loads(_safe_decode(raw))
        if m["id"] == message_id:
            if m["sender_id"] != str(actor_id):
                return False, "You can only edit your own messages."
            m["content"] = encrypt_message(new_content, group["key"].encode())
            m["edited"] = True
            r.lset(_messages_key(gid), i, json.dumps(m))
            return True, None
    return False, "Message not found."


def delete_message(gid, message_id, actor_id):
    """
    WhatsApp clause: sender can delete their own message for everyone;
    admins can delete ANY message for everyone (moderation).
    """
    r = _redis()
    raw_all = r.lrange(_messages_key(gid), 0, -1)

    for i, raw in enumerate(raw_all):
        m = json.loads(_safe_decode(raw))
        if m["id"] == message_id:
            if m["sender_id"] != str(actor_id) and not is_admin(gid, actor_id):
                return False, "You don't have permission to delete this message."
            m["deleted"] = True
            m["content"] = ""
            m["file_url"] = None
            r.lset(_messages_key(gid), i, json.dumps(m))
            return True, None
    return False, "Message not found."


def _user_unread_key(uid):
    return f"user:group_unread:{uid}"


def increment_unread_for_others(gid, sender_id):
    """Bump the unread counter for every member except the sender."""
    r = _redis()
    for m in list_members(gid):
        uid = m["user_id"]
        if str(uid) == str(sender_id):
            continue
        r.hincrby(_user_unread_key(uid), gid, 1)


def get_all_unread(user_id):
    """{gid: unread_count} for every group/channel this user belongs to."""
    raw = _redis().hgetall(_user_unread_key(user_id))
    return {_safe_decode(k): int(_safe_decode(v)) for k, v in raw.items()}


def clear_unread(gid, user_id):
    _redis().hdel(_user_unread_key(user_id), gid)


def get_total_unread(user_id):
    """Sum of all unread counts across every group/channel this user is in —
    used for the global nav badge, independent of which page they're on."""
    unread_map = get_all_unread(user_id)
    return sum(unread_map.values())


# ─────────────────────────────────────────────────────────────────────────────
# PINNED MESSAGES (WhatsApp + Telegram clause: admins pin)
# ─────────────────────────────────────────────────────────────────────────────

def pin_message(gid, actor_id, message_id):
    if not is_admin(gid, actor_id):
        return False, "Only admins can pin messages."
    r = _redis()
    r.lrem(_pinned_key(gid), 0, message_id)
    r.rpush(_pinned_key(gid), message_id)
    r.ltrim(_pinned_key(gid), -50, -1)  # keep last 50 pins
    return True, None


def unpin_message(gid, actor_id, message_id):
    if not is_admin(gid, actor_id):
        return False, "Only admins can unpin messages."
    _redis().lrem(_pinned_key(gid), 0, message_id)
    return True, None


def list_pinned(gid):
    ids = [_safe_decode(x) for x in _redis().lrange(_pinned_key(gid), 0, -1)]
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# READ RECEIPTS
# ─────────────────────────────────────────────────────────────────────────────

def set_last_read(gid, user_id, message_id):
    _redis().hset(_reads_key(gid), str(user_id), message_id)


def get_read_receipts(gid):
    raw = _redis().hgetall(_reads_key(gid))
    return {_safe_decode(k): _safe_decode(v) for k, v in raw.items()}


# ─────────────────────────────────────────────────────────────────────────────
# BROADCAST-SPECIFIC: per-post view counts (Telegram clause)
# ─────────────────────────────────────────────────────────────────────────────

def register_view(gid, message_id, user_id):
    _redis().sadd(_views_key(gid, message_id), str(user_id))


def get_view_count(gid, message_id):
    return _redis().scard(_views_key(gid, message_id))


# ─────────────────────────────────────────────────────────────────────────────
# MUTE (per-user notification preference — not a role change)
# ─────────────────────────────────────────────────────────────────────────────

def mute_group_for_user(gid, user_id, muted=True):
    r = _redis()
    if muted:
        r.sadd(_user_mute_key(user_id), gid)
    else:
        r.srem(_user_mute_key(user_id), gid)


def is_muted_for_user(gid, user_id):
    return _redis().sismember(_user_mute_key(user_id), gid)




def get_group_by_invite_code(code):
    """Peek at the group an invite code points to, WITHOUT joining."""
    gid = _redis().get(_invite_key(code))
    if not gid:
        return None
    return get_group(_safe_decode(gid))


def search_public_channels(query, exclude_user_id=None, limit=30):
    """
    Naive substring search over the public-channel index. Fine at the scale
    Redis-backed groups are meant for — same philosophy as the rest of this
    file (no full-text engine, just a scan over a bounded set).
    """
    r = _redis()
    query = (query or "").strip().lower()
    gids = r.smembers(PUBLIC_GROUPS_INDEX_KEY)

    results = []
    for raw_gid in gids:
        gid = _safe_decode(raw_gid)
        g = get_group(gid)
        if not g or not g.get("is_public") or g.get("kind") != "broadcast":
            r.srem(PUBLIC_GROUPS_INDEX_KEY, gid)   # stale entry — self-heal
            continue

        if exclude_user_id is not None and is_member(gid, exclude_user_id):
            continue

        if not query:
            results.append(g)
            continue

        haystack = f"{g.get('name','')} {g.get('channel_username','')} {g.get('description','')}".lower()
        if query in haystack:
            results.append(g)

    results.sort(key=lambda g: g["member_count"], reverse=True)
    return results[:limit]
