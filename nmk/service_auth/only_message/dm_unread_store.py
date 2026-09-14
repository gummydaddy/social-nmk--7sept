# nmk/service_auth/only_message/dm_unread_store.py
#
# Per-user unread counters for 1:1 direct messages — same Redis-hash
# pattern as group_store's unread tracking (user:group_unread:{uid}),
# kept in its own file since DM messages live in Postgres (Message model)
# while this counter, like the group one, is a lightweight Redis-only
# supporting layer. No migrations, no changes to the Message model.

from django_redis import get_redis_connection


def _redis():
    return get_redis_connection("default")


def _safe_decode(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _dm_unread_key(uid):
    return f"user:dm_unread:{uid}"


def increment_dm_unread(sender_id, recipient_id):
    """Call once, right after a message is successfully saved."""
    _redis().hincrby(_dm_unread_key(recipient_id), str(sender_id), 1)


def get_dm_unread_map(user_id):
    """{other_user_id: unread_count} for every conversation this user has."""
    raw = _redis().hgetall(_dm_unread_key(user_id))
    return {_safe_decode(k): int(_safe_decode(v)) for k, v in raw.items()}


def get_dm_unread_count(user_id, other_user_id):
    val = _redis().hget(_dm_unread_key(user_id), str(other_user_id))
    return int(_safe_decode(val)) if val else 0


def get_total_dm_unread(user_id):
    return sum(get_dm_unread_map(user_id).values())


def clear_dm_unread(user_id, other_user_id):
    """Call when the user opens/views their conversation with other_user_id."""
    _redis().hdel(_dm_unread_key(user_id), str(other_user_id))
