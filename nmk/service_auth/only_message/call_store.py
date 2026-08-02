import json
import time
import uuid
import logging

from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

CALL_KEY_PREFIX = "call:pending:"
CALL_ICE_PREFIX = "call:ice:"
RING_TTL = 60   # seconds a call stays answerable
ICE_TTL = 90    # a bit longer so late-arriving ICE isn't lost


def _redis():
    return get_redis_connection("default")


def create_pending_call(caller_id, caller_username, caller_pic, callee_id, call_type, offer):
    call_id = uuid.uuid4().hex
    payload = {
        "call_id": call_id,
        "caller_id": caller_id,
        "caller": caller_username,
        "caller_pic": caller_pic or "",
        "callee_id": callee_id,
        "call_type": call_type,
        "offer": offer,
        "status": "ringing",
        "created_at": time.time(),
    }
    try:
        _redis().set(f"{CALL_KEY_PREFIX}{call_id}", json.dumps(payload), ex=RING_TTL)
    except Exception as e:
        logger.error("create_pending_call failed: %s", e)
    return call_id


def get_pending_call(call_id):
    try:
        raw = _redis().get(f"{CALL_KEY_PREFIX}{call_id}")
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.error("get_pending_call failed: %s", e)
        return None


def mark_call_answered(call_id):
    try:
        _redis().delete(f"{CALL_KEY_PREFIX}{call_id}")
    except Exception as e:
        logger.warning("mark_call_answered failed: %s", e)


def end_pending_call(call_id):
    try:
        r = _redis()
        r.delete(f"{CALL_KEY_PREFIX}{call_id}")
        r.delete(f"{CALL_ICE_PREFIX}{call_id}")
    except Exception as e:
        logger.warning("end_pending_call failed: %s", e)


def queue_ice_candidate(call_id, candidate, from_user_id):
    try:
        r = _redis()
        key = f"{CALL_ICE_PREFIX}{call_id}"
        r.rpush(key, json.dumps({"candidate": candidate, "from_user_id": from_user_id}))
        r.expire(key, ICE_TTL)
    except Exception as e:
        logger.warning("queue_ice_candidate failed: %s", e)


def drain_ice_candidates(call_id, exclude_user_id=None):
    try:
        r = _redis()
        key = f"{CALL_ICE_PREFIX}{call_id}"
        raw_items = r.lrange(key, 0, -1)
        r.delete(key)
        out = []
        for raw in raw_items:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                item = json.loads(raw)
                if exclude_user_id is None or item.get("from_user_id") != exclude_user_id:
                    out.append(item["candidate"])
            except Exception:
                continue
        return out
    except Exception as e:
        logger.warning("drain_ice_candidates failed: %s", e)
        return []
