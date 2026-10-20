"""
Server-Sent Events (SSE) engine with Redis Pub/Sub multi-worker scaling.

Architecture:
- In single-worker / development mode (no REDIS_URL), uses thread-safe in-memory
  queues per user.
- In multi-worker production mode (with REDIS_URL), events published by any Gunicorn
  worker are broadcast via Redis Pub/Sub channel 'opencampus:sse:{user_id}' and
  'opencampus:sse:broadcast'.
- Every connected client generator subscribes to the Redis Pub/Sub channel (or local queue)
  and streams events, sending heartbeats every 25s and auto-recycling connections at 300s.
- Graceful degradation: If Redis becomes unreachable, it falls back to the in-memory queue.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import Generator

logger = logging.getLogger("opencampus.sse")

# ---------------------------------------------------------------------------
# In-memory queues (single-process / fallback)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_USER_QUEUES: dict[int, list[queue.Queue]] = {}

_HEARTBEAT_INTERVAL = 25  # seconds between keepalive pings
_CLIENT_TIMEOUT = 300      # max seconds a client stays connected before reconnecting

# ---------------------------------------------------------------------------
# Redis Pub/Sub Backend
# ---------------------------------------------------------------------------
_redis_client = None
_redis_initialized = False
_redis_lock = threading.Lock()


def get_redis_client():
    """Lazily initialize and return a shared Redis client if configured."""
    global _redis_client, _redis_initialized
    if not _redis_initialized:
        with _redis_lock:
            if not _redis_initialized:
                redis_url = os.environ.get("REDIS_URL", "").strip()
                if redis_url:
                    try:
                        import redis
                        _redis_client = redis.from_url(redis_url, decode_responses=True)
                        _redis_client.ping()
                        logger.info("SSE Redis Pub/Sub backend connected: %s", redis_url.split("@")[-1])
                    except Exception as exc:
                        logger.warning("Failed to connect to Redis for SSE (%s); falling back to in-memory queues", exc)
                        _redis_client = None
                _redis_initialized = True
    return _redis_client


def _subscribe_local(user_id: int) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=50)
    with _lock:
        _USER_QUEUES.setdefault(user_id, []).append(q)
    return q


def _unsubscribe_local(user_id: int, q: queue.Queue) -> None:
    with _lock:
        bucket = _USER_QUEUES.get(user_id, [])
        try:
            bucket.remove(q)
        except ValueError:
            pass
        if not bucket:
            _USER_QUEUES.pop(user_id, None)


def push_event(user_id: int, event_type: str, data: dict) -> int:
    """
    Push an SSE event to user_id across all workers via Redis Pub/Sub,
    falling back to local in-memory queues.
    """
    payload_str = json.dumps({"event": event_type, "data": data}, default=str)
    sent = 0

    # 1. Distribute via Redis Pub/Sub if available
    r = get_redis_client()
    if r is not None:
        try:
            channel = f"opencampus:sse:{user_id}"
            listeners = r.publish(channel, payload_str)
            logger.debug("Published SSE event to Redis channel %s (subscribers: %d)", channel, listeners)
            sent += listeners
        except Exception as exc:
            logger.warning("Redis publish failed (%s); using in-memory queues", exc)

    # 2. Always populate local process queues as well
    with _lock:
        queues = list(_USER_QUEUES.get(user_id, []))
    for q in queues:
        try:
            q.put_nowait({"event": event_type, "data": json.dumps(data, default=str)})
            sent += 1
        except queue.Full:
            logger.warning("Local SSE queue full for user %s, dropping event %s", user_id, event_type)

    return sent


def push_event_to_all(event_type: str, data: dict) -> int:
    """Broadcast an event to every connected user across all workers."""
    payload_str = json.dumps({"event": event_type, "data": data}, default=str)
    sent = 0

    r = get_redis_client()
    if r is not None:
        try:
            listeners = r.publish("opencampus:sse:broadcast", payload_str)
            sent += listeners
        except Exception as exc:
            logger.warning("Redis broadcast failed (%s); using in-memory queues", exc)

    with _lock:
        user_ids = list(_USER_QUEUES.keys())
    for uid in user_ids:
        sent += push_event(uid, event_type, data)

    return sent


def _format_sse(event_type: str, data: str, event_id: int | None = None) -> str:
    """Serialise one SSE frame with proper line breaks and terminator."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    for line in data.splitlines():
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def event_stream(user_id: int) -> Generator[str, None, None]:
    """
    Generator consumed by Flask's streaming response for one SSE client.
    Listens to Redis Pub/Sub if available, or drains local queue.
    """
    logger.debug("SSE client connected: user_id=%s", user_id)
    deadline = time.monotonic() + _CLIENT_TIMEOUT
    event_id = 0

    r = get_redis_client()
    if r is not None:
        # --- Redis Pub/Sub path (Multi-worker Gunicorn) ---
        pubsub = None
        try:
            pubsub = r.pubsub(ignore_subscribe_messages=True)
            user_channel = f"opencampus:sse:{user_id}"
            pubsub.subscribe(user_channel, "opencampus:sse:broadcast")

            while time.monotonic() < deadline:
                message = pubsub.get_message(timeout=_HEARTBEAT_INTERVAL)
                if message and message.get("type") == "message":
                    try:
                        parsed = json.loads(message["data"])
                        event_id += 1
                        data_content = parsed["data"]
                        if not isinstance(data_content, str):
                            data_content = json.dumps(data_content)
                        yield _format_sse(parsed["event"], data_content, event_id)
                    except Exception as err:
                        logger.error("Failed to parse SSE Redis message: %s", err)
                else:
                    # Heartbeat keeps proxy (Nginx) and browser connection alive
                    yield ": heartbeat\n\n"
        except Exception as exc:
            logger.warning("Redis pubsub stream error (%s); falling back to local queue", exc)
        finally:
            if pubsub is not None:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception:
                    pass
            logger.debug("SSE client disconnected: user_id=%s", user_id)
            return

    # --- In-memory fallback path (Single process / dev mode) ---
    q = _subscribe_local(user_id)
    try:
        while time.monotonic() < deadline:
            try:
                item = q.get(timeout=_HEARTBEAT_INTERVAL)
                event_id += 1
                yield _format_sse(item["event"], item["data"], event_id)
            except queue.Empty:
                yield ": heartbeat\n\n"
    finally:
        _unsubscribe_local(user_id, q)
        logger.debug("SSE client disconnected: user_id=%s", user_id)
