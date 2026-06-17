# nmk/service_auth/only_message/stranger_consumer.py
#
# Random "Omegle-style" video chat.
#
# - Matchmaking queue lives in Redis (no DB models / migrations).
# - WebRTC signalling (offer/answer/ICE) is relayed peer-to-peer
#   between the two matched consumers via channel_layer.send(),
#   so the server never touches media — keeps it light.

import json
import time
import uuid
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

QUEUE_KEY = "stranger:queue"
QUEUE_MAX_AGE = 90       # seconds — stale waiting entries get dropped
QUEUE_SCAN_LIMIT = 200   # cap how many waiting entries we scan per find


def _redis():
    return get_redis_connection("default")


@sync_to_async
def _get_user_info(user):
    info = {
        "user_id": user.id,
        "username": user.username,
        "pic": "",
        "country": "ANY",
    }
    try:
        profile = user.profile
        if profile.profile_picture:
            info["pic"] = profile.profile_picture.url
        if profile.country:
            info["country"] = str(profile.country)  # e.g. "US"
    except Exception:
        pass
    return info


@sync_to_async
def _queue_push(entry):
    _redis().rpush(QUEUE_KEY, json.dumps(entry, sort_keys=True))


@sync_to_async
def _queue_snapshot():
    return _redis().lrange(QUEUE_KEY, 0, QUEUE_SCAN_LIMIT - 1)


@sync_to_async
def _queue_remove(raw):
    return _redis().lrem(QUEUE_KEY, 1, raw)


class StrangerChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            logger.warning("Unauthenticated user tried to connect to /ws/stranger/")
            await self.close()
            return

        self.partner_channel = None
        self.room_id = None
        self.want_country = "ANY"
        self.in_queue = False
        self.info = await _get_user_info(self.user)

        await self.accept()
        logger.info(f"🎥 Stranger WS connected: {self.user.username}")

    async def disconnect(self, close_code):
        await self._leave_queue()
        await self._notify_partner_left("disconnected")
        logger.info(f"🎥 Stranger WS disconnected: {self.user.username}")

    # ──────────────────────────────────────────────────────────
    #  INCOMING
    # ──────────────────────────────────────────────────────────
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError):
            return

        t = data.get("type")

        if t == "find":
            self.want_country = (data.get("country") or "ANY").upper()
            await self._find_partner()

        elif t == "skip":
            await self._skip()

        elif t == "stop":
            await self._stop()

        elif t in ("webrtc_offer", "webrtc_answer", "ice_candidate"):
            await self._relay_signal(t, data)

        elif t == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    # ──────────────────────────────────────────────────────────
    #  MATCHMAKING
    # ──────────────────────────────────────────────────────────
    async def _find_partner(self):
        if self.partner_channel:
            await self._leave_room("skip")

        now = time.time()
        raw_entries = await _queue_snapshot()

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
            except (ValueError, TypeError):
                await _queue_remove(raw)
                continue

            # drop stale entries while we scan
            if now - entry.get("ts", 0) > QUEUE_MAX_AGE:
                await _queue_remove(raw)
                continue

            if entry.get("channel") == self.channel_name:
                continue

            entry_country = entry.get("country", "ANY")
            entry_want = entry.get("want", "ANY")

            compatible = (
                (self.want_country == "ANY" or self.want_country == entry_country)
                and (entry_want == "ANY" or entry_want == self.info["country"])
            )
            if not compatible:
                continue

            # try to claim this candidate
            removed = await _queue_remove(raw)
            if not removed:
                continue  # someone else grabbed it first — keep scanning

            await self._pair_with(entry)
            return

        # nothing compatible — wait in the queue
        await self._enter_queue()
        await self.send(text_data=json.dumps({"type": "searching"}))

    async def _enter_queue(self):
        entry = {
            "channel": self.channel_name,
            "user_id": self.info["user_id"],
            "username": self.info["username"],
            "pic": self.info["pic"],
            "country": self.info["country"],
            "want": self.want_country,
            "ts": time.time(),
        }
        await _queue_push(entry)
        self.in_queue = True

    async def _leave_queue(self):
        if not self.in_queue:
            return
        for raw in await _queue_snapshot():
            try:
                entry = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if entry.get("channel") == self.channel_name:
                await _queue_remove(raw)
        self.in_queue = False

    async def _pair_with(self, partner_entry):
        self.in_queue = False
        self.room_id = uuid.uuid4().hex
        self.partner_channel = partner_entry["channel"]

        # We (the searcher) act as the WebRTC offerer.
        await self.send(text_data=json.dumps({
            "type": "matched",
            "role": "offerer",
            "room_id": self.room_id,
            "partner": {
                "username": partner_entry["username"],
                "pic": partner_entry["pic"],
                "country": partner_entry["country"],
            },
        }))

        try:
            await self.channel_layer.send(self.partner_channel, {
                "type": "stranger.matched",
                "room_id": self.room_id,
                "partner_channel": self.channel_name,
                "partner": {
                    "username": self.info["username"],
                    "pic": self.info["pic"],
                    "country": self.info["country"],
                },
            })
        except Exception as e:
            logger.warning(f"Failed to notify matched partner: {e}")
            # partner channel was stale — try again
            self.partner_channel = None
            self.room_id = None
            await self._find_partner()

    # event sent to the OTHER (waiting) consumer
    async def stranger_matched(self, event):
        self.partner_channel = event["partner_channel"]
        self.room_id = event["room_id"]
        self.in_queue = False
        await self.send(text_data=json.dumps({
            "type": "matched",
            "role": "answerer",
            "room_id": self.room_id,
            "partner": event["partner"],
        }))

    # ──────────────────────────────────────────────────────────
    #  SIGNALLING — pure relay (offer / answer / ICE)
    # ──────────────────────────────────────────────────────────
    async def _relay_signal(self, t, data):
        if not self.partner_channel:
            return
        try:
            await self.channel_layer.send(self.partner_channel, {
                "type": "stranger.signal",
                "signal_type": t,
                "payload": data.get("payload"),
            })
        except Exception as e:
            logger.warning(f"Signal relay failed: {e}")

    async def stranger_signal(self, event):
        await self.send(text_data=json.dumps({
            "type": event["signal_type"],
            "payload": event["payload"],
        }))

    # ──────────────────────────────────────────────────────────
    #  SKIP / STOP / LEAVE
    # ──────────────────────────────────────────────────────────
    async def _skip(self):
        await self._leave_room("skip")
        await self._find_partner()

    async def _stop(self):
        await self._leave_room("stop")
        await self._leave_queue()
        await self.send(text_data=json.dumps({"type": "stopped"}))

    async def _leave_room(self, reason):
        await self._notify_partner_left(reason)
        self.partner_channel = None
        self.room_id = None

    async def _notify_partner_left(self, reason):
        if self.partner_channel:
            try:
                await self.channel_layer.send(self.partner_channel, {
                    "type": "stranger.partner_left",
                    "reason": reason,
                })
            except Exception:
                pass

    async def stranger_partner_left(self, event):
        self.partner_channel = None
        self.room_id = None
        await self.send(text_data=json.dumps({
            "type": "partner_left",
            "reason": event.get("reason"),
        }))
