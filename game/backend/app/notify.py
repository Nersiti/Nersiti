"""Outgoing Telegram messages go through a Redis queue drained by the worker.

API handlers and jobs never call the Bot API for notifications directly: the worker
applies Telegram's rate limits (≈25 msg/s overall, 1 msg/s per chat).
"""

import json
from datetime import UTC, datetime

from app.config import get_settings
from app.redis_client import get_redis

QUEUE_KEY = "notify:queue"
DAILY_PERSONAL_LIMIT = 5


def webapp_button(text: str, start_param: str | None = None) -> dict:
    url = get_settings().webapp_url
    if start_param:
        url = f"{url}?sp={start_param}"
    return {"text": text, "web_app": url}


def url_button(text: str, url: str) -> dict:
    return {"text": text, "url": url}


async def enqueue(
    chat_id: int,
    text: str,
    *,
    button: dict | None = None,
    user_id: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Queues a message. Personal messages (user_id set) are capped per user per day.
    Returns False if the message was dropped by the cap."""
    redis = get_redis()
    if user_id is not None:
        day = (now or datetime.now(UTC)).strftime("%Y%m%d")
        key = f"notify:count:{user_id}:{day}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 2 * 86400)
        if count > DAILY_PERSONAL_LIMIT:
            return False
    item = {"chat_id": chat_id, "text": text, "button": button, "user_id": user_id}
    await redis.rpush(QUEUE_KEY, json.dumps(item, ensure_ascii=False))
    return True
