import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode


def make_init_data(
    user_id: int,
    first_name: str = "Test",
    *,
    auth_date: int | None = None,
    start_param: str | None = None,
    language_code: str = "ru",
    is_premium: bool = False,
    token: str | None = None,
) -> str:
    """Builds initData signed exactly like Telegram does."""
    token = token or os.environ["BOT_TOKEN"]
    user = {"id": user_id, "first_name": first_name, "language_code": language_code}
    if is_premium:
        user["is_premium"] = True
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH-test",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    if start_param:
        fields["start_param"] = start_param
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def auth(user_id: int, **kwargs) -> dict[str, str]:
    return {"Authorization": f"tma {make_init_data(user_id, **kwargs)}"}


async def login(client, user_id: int, **kwargs) -> dict:
    body = kwargs.pop("body", {})
    res = await client.post("/api/session", json=body, headers=auth(user_id, **kwargs))
    assert res.status_code == 200, res.text
    return res.json()
