import time
from urllib.parse import parse_qsl, urlencode

import pytest

from app.auth import AuthError, validate_init_data
from app.config import get_settings
from app.models import User
from tests.helpers import auth, login, make_init_data

TOKEN = get_settings().bot_token


def test_valid_init_data():
    identity = validate_init_data(make_init_data(5, "Anna", start_param="r_1"), TOKEN, 86400)
    assert identity.id == 5
    assert identity.first_name == "Anna"
    assert identity.start_param == "r_1"


def test_tampered_init_data_rejected():
    fields = dict(parse_qsl(make_init_data(5)))
    fields["user"] = fields["user"].replace('"id":5', '"id":6')
    with pytest.raises(AuthError, match="bad_signature"):
        validate_init_data(urlencode(fields), TOKEN, 86400)


def test_wrong_token_rejected():
    data = make_init_data(5, token="987654321:OTHER-token_abcdefghijklmnopqrstuv")
    with pytest.raises(AuthError, match="bad_signature"):
        validate_init_data(data, TOKEN, 86400)


def test_expired_init_data_rejected():
    data = make_init_data(5, auth_date=int(time.time()) - 86400 - 60)
    with pytest.raises(AuthError, match="expired"):
        validate_init_data(data, TOKEN, 86400)


async def test_session_requires_auth(client):
    assert (await client.post("/api/session", json={})).status_code == 401
    res = await client.post("/api/session", json={}, headers={"Authorization": "tma garbage"})
    assert res.status_code == 401


async def test_dev_header_rejected_without_dev_mode(client):
    res = await client.post("/api/session", json={}, headers={"Authorization": "dev 1"})
    assert res.status_code == 401


async def test_session_creates_then_updates_user(client, db):
    first = await login(client, 100, first_name="Old")
    assert first["created"] is True
    assert first["state"]["user"]["first_name"] == "Old"
    assert first["state"]["coins"] == 1000
    assert first["config"]["bot_username"] == "test_bot"

    second = await login(client, 100, first_name="New")
    assert second["created"] is False
    user = await db.get(User, 100)
    assert user.first_name == "New"


async def test_referrer_saved_only_for_existing_user_on_first_visit(client, db):
    await login(client, 1)
    await login(client, 2, start_param="r_1")
    await login(client, 3, start_param="r_424242")  # unknown inviter
    await login(client, 4, body={"start_param": "r_1"})  # ?sp= fallback
    await login(client, 1, start_param="r_2")  # existing user: ignored

    assert (await db.get(User, 2)).referrer_id == 1
    assert (await db.get(User, 3)).referrer_id is None
    assert (await db.get(User, 4)).referrer_id == 1
    assert (await db.get(User, 1)).referrer_id is None


async def test_self_referral_ignored(client, db):
    await login(client, 7, start_param="r_7")
    assert (await db.get(User, 7)).referrer_id is None


async def test_banned_user_gets_403(client, db):
    await login(client, 50)
    user = await db.get(User, 50)
    user.banned = True
    await db.commit()
    res = await client.post("/api/session", json={}, headers=auth(50))
    assert res.status_code == 403


async def test_dev_header_accepted_in_dev_mode(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "dev_mode", True)
    res = await client.post("/api/session", json={}, headers={"Authorization": "dev 77"})
    assert res.status_code == 200
    assert res.json()["state"]["user"]["id"] == 77


def test_dev_mode_forbidden_in_prod():
    from app.config import Settings

    settings = Settings(env="prod", dev_mode=True, bot_token="1:x", webhook_secret="x")
    with pytest.raises(RuntimeError):
        settings.check_safety()
