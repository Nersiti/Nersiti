from datetime import timedelta

import pytest
from aiogram.types import ChatInviteLink, ChatMemberAdministrator, ChatMemberLeft, ChatMemberMember
from aiogram.types import User as TgUser
from sqlalchemy import func, select

from app.game import clan_service, player_service
from app.models import Clan, User
from tests.helpers import auth, login, seed_world

WEBHOOK = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


def tg_user(user_id: int, is_bot: bool = False) -> TgUser:
    return TgUser(id=user_id, is_bot=is_bot, first_name="x")


def member(user_id: int, status: str):
    u = tg_user(user_id)
    if status == "member":
        return ChatMemberMember(user=u)
    if status == "left":
        return ChatMemberLeft(user=u)
    return ChatMemberAdministrator(
        user=u,
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_send_welcome_messages=False,
    )


async def onboard(client, user_id: int, city_id: int, **kwargs) -> dict:
    await login(client, user_id, **kwargs)
    res = await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": city_id}, headers=auth(user_id)
    )
    assert res.status_code == 200, res.text
    return res.json()["state"]


async def make_channel_clan(db, chat_id=-1001, subscribers_only=False, owner=1) -> Clan:
    clan = Clan(
        kind="channel",
        tg_chat_id=chat_id,
        title="Мой канал",
        username="my_channel",
        owner_user_id=owner,
        subscribers_only=subscribers_only,
        members_count=0,
    )
    db.add(clan)
    await db.commit()
    return clan


async def test_onboarding_joins_city_militia(client, db):
    ids = await seed_world(db)
    s1 = await onboard(client, 1, ids["kazan"])
    s2 = await onboard(client, 2, ids["kazan"])
    s3 = await onboard(client, 3, ids["moscow"])
    assert s1["clan"]["is_militia"] is True
    assert s1["clan"]["title"] == "Ополчение: Казань"
    assert s1["clan"]["id"] == s2["clan"]["id"] != s3["clan"]["id"]
    militia = await db.get(Clan, s1["clan"]["id"])
    await db.refresh(militia)
    assert militia.members_count == 2
    assert militia.color.startswith("#") and militia.color != "#888888"


async def test_invite_link_returned_and_join_leave(client, db):
    ids = await seed_world(db)
    clan = await make_channel_clan(db)
    session = await login(client, 1, start_param=f"c_{clan.id}")
    assert session["invite_clan"]["title"] == "Мой канал"
    await onboard(client, 1, ids["kazan"])

    res = await client.post(f"/api/clans/{clan.id}/join", headers=auth(1))
    assert res.status_code == 200, res.text
    assert res.json()["state"]["clan"]["id"] == clan.id

    details = (await client.get(f"/api/clans/{clan.id}", headers=auth(1))).json()
    assert details["members_count"] == 1
    assert details["is_member"] is True
    assert details["invite_link"] == f"https://t.me/test_bot?startapp=c_{clan.id}"

    res = await client.post("/api/clans/leave", headers=auth(1))
    assert res.json()["state"]["clan"]["is_militia"] is True
    await db.refresh(clan)
    assert clan.members_count == 0


async def test_clan_switch_cooldown(client, db, monkeypatch):
    ids = await seed_world(db)
    a = await make_channel_clan(db, chat_id=-1001)
    b = await make_channel_clan(db, chat_id=-1002)
    await onboard(client, 1, ids["kazan"])
    assert (await client.post(f"/api/clans/{a.id}/join", headers=auth(1))).status_code == 200
    res = await client.post(f"/api/clans/{b.id}/join", headers=auth(1))
    assert res.status_code == 409
    assert res.json()["detail"] == "clan_cooldown"
    # Leaving to the militia does not reset the cooldown.
    await client.post("/api/clans/leave", headers=auth(1))
    assert (await client.post(f"/api/clans/{b.id}/join", headers=auth(1))).status_code == 409

    later = player_service.utcnow() + timedelta(hours=25)
    monkeypatch.setattr(player_service, "utcnow", lambda: later)
    assert (await client.post(f"/api/clans/{b.id}/join", headers=auth(1))).status_code == 200


async def test_cannot_join_foreign_militia_or_without_onboarding(client, db):
    ids = await seed_world(db)
    moscow_state = await onboard(client, 2, ids["moscow"])
    await login(client, 1)
    res = await client.post(f"/api/clans/{moscow_state['clan']['id']}/join", headers=auth(1))
    assert res.json()["detail"] == "onboarding_required"
    await onboard(client, 1, ids["kazan"])
    res = await client.post(f"/api/clans/{moscow_state['clan']['id']}/join", headers=auth(1))
    assert res.status_code == 403
    assert res.json()["detail"] == "foreign_militia"


async def test_subscribers_only_requires_subscription(client, db, bot_session):
    ids = await seed_world(db)
    clan = await make_channel_clan(db, subscribers_only=True)
    await onboard(client, 1, ids["kazan"])

    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "left")
    res = await client.post(f"/api/clans/{clan.id}/join", headers=auth(1))
    assert res.status_code == 403
    assert res.json()["detail"] == "subscribe_required"

    from app.redis_client import get_redis

    await get_redis().delete(f"sub:{clan.tg_chat_id}:1")  # negative cache expired
    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "member")
    res = await client.post(f"/api/clans/{clan.id}/join", headers=auth(1))
    assert res.status_code == 200


async def test_unsubscribed_member_moved_to_militia_on_session(client, db, bot_session):
    ids = await seed_world(db)
    clan = await make_channel_clan(db, subscribers_only=True)
    await onboard(client, 1, ids["kazan"])
    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "member")
    await client.post(f"/api/clans/{clan.id}/join", headers=auth(1))

    from app.redis_client import get_redis

    await get_redis().flushdb()
    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "left")
    session = await login(client, 1)
    assert session["state"]["clan"]["is_militia"] is True


async def test_top_clans(client, db):
    ids = await seed_world(db)
    await onboard(client, 1, ids["kazan"])
    await onboard(client, 2, ids["moscow"])
    await db.execute(
        Clan.__table__.update().where(Clan.city_id == ids["moscow"]).values(season_points=50)
    )
    await db.commit()
    items = (await client.get("/api/clans/top", headers=auth(1))).json()["items"]
    assert [i["title"] for i in items] == ["Ополчение: Москва", "Ополчение: Казань"]


# --- Bot: /newclan -------------------------------------------------------------------


def private_message(text=None, user_id=1, **extra) -> dict:
    msg = {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "language_code": "ru"},
        **extra,
    }
    if text:
        msg["text"] = text
        msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"update_id": 1, "message": msg}


async def test_newclan_prompt_offers_chat_pickers(client, bot_session):
    await client.post("/tg/webhook", json=private_message("/newclan"), headers=WEBHOOK)
    [sent] = bot_session.of_type("SendMessage")
    buttons = [row[0] for row in sent.reply_markup.keyboard]
    assert buttons[0].request_chat.chat_is_channel is True
    assert buttons[1].request_chat.chat_is_channel is False
    assert buttons[1].request_chat.bot_is_member is True


def chat_shared_update(request_id: int, chat_id: int, title: str = "Мой канал") -> dict:
    return private_message(
        chat_shared={
            "request_id": request_id,
            "chat_id": chat_id,
            "title": title,
            "username": "my_channel",
        }
    )


async def test_newclan_creates_clan_from_channel(client, db, bot_session):
    from app.bot.instance import get_bot

    bot_id = get_bot().id
    bot_session.responses["GetChatMember"] = lambda m: member(
        m.user_id, "administrator" if m.user_id in (1, bot_id) else "left"
    )
    bot_session.responses["GetChatMemberCount"] = 500

    await client.post("/tg/webhook", json=chat_shared_update(1, -100500), headers=WEBHOOK)

    clan = (await db.execute(select(Clan).where(Clan.tg_chat_id == -100500))).scalar_one()
    assert clan.kind == "channel"
    assert clan.owner_user_id == 1
    texts = [m.text for m in bot_session.of_type("SendMessage")]
    assert f"https://t.me/test_bot?startapp=c_{clan.id}" in texts[0]

    # Owner toggles "subscribers only" and publishes the invite post.
    from app.bot.handlers.clans import ClanCb

    def callback(action: str) -> dict:
        return {
            "update_id": 2,
            "callback_query": {
                "id": "cb1",
                "chat_instance": "ci",
                "from": {"id": 1, "is_bot": False, "first_name": "Owner", "language_code": "ru"},
                "data": ClanCb(action=action, clan_id=clan.id).pack(),
            },
        }

    await client.post("/tg/webhook", json=callback("subs"), headers=WEBHOOK)
    await db.refresh(clan)
    assert clan.subscribers_only is True

    await client.post("/tg/webhook", json=callback("post"), headers=WEBHOOK)
    post = bot_session.of_type("SendMessage")[-1]
    assert post.chat_id == -100500
    assert post.reply_markup.inline_keyboard[0][0].url.endswith(f"c_{clan.id}")


async def test_newclan_rejects_small_or_foreign_chat(client, db, bot_session):
    from app.bot.instance import get_bot

    bot_id = get_bot().id
    bot_session.responses["GetChatMember"] = lambda m: member(
        m.user_id, "administrator" if m.user_id == bot_id else "member"
    )
    bot_session.responses["GetChatMemberCount"] = 500
    await client.post("/tg/webhook", json=chat_shared_update(1, -1), headers=WEBHOOK)
    assert "администратор" in bot_session.of_type("SendMessage")[-1].text

    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "administrator")
    bot_session.responses["GetChatMemberCount"] = 5
    await client.post("/tg/webhook", json=chat_shared_update(1, -2), headers=WEBHOOK)
    assert "минимум 10" in bot_session.of_type("SendMessage")[-1].text

    bot_session.responses["GetChatMemberCount"] = 50
    await client.post("/tg/webhook", json=chat_shared_update(1, -3, "Fuck war"), headers=WEBHOOK)
    assert "модерацию" in bot_session.of_type("SendMessage")[-1].text

    count = (await db.execute(select(func.count()).select_from(Clan))).scalar_one()
    assert count == 0


async def test_bot_kicked_disables_subscribers_only(client, db, bot_session):
    clan = await make_channel_clan(db, chat_id=-777, subscribers_only=True)
    bot_admin = member(42, "administrator").model_dump(mode="json", exclude_none=True)
    bot_left = member(42, "left").model_dump(mode="json", exclude_none=True)
    update = {
        "update_id": 3,
        "my_chat_member": {
            "chat": {"id": -777, "type": "channel", "title": "Мой канал"},
            "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
            "date": 1700000000,
            "old_chat_member": bot_admin,
            "new_chat_member": bot_left,
        },
    }
    await client.post("/tg/webhook", json=update, headers=WEBHOOK)
    await db.refresh(clan)
    assert clan.subscribers_only is False


def test_clan_param_and_colors():
    assert clan_service.parse_clan_param("c_15") == 15
    assert clan_service.parse_clan_param("r_15") is None
    assert clan_service.parse_clan_param(None) is None
    colors = {clan_service.clan_color(i) for i in range(1, 50)}
    assert len(colors) == 49


@pytest.mark.parametrize(
    ("title", "allowed"),
    [("Школа 57", True), ("Свободный", True), ("ху й", False), ("Nazi club", False)],
)
def test_title_moderation(title, allowed):
    from app.moderation import is_allowed

    assert is_allowed(title) is allowed


async def test_invite_link_created_for_private_channel(client, db, bot_session):
    clan = await make_channel_clan(db, chat_id=-888)
    clan.username = None
    await db.commit()
    bot_session.responses["CreateChatInviteLink"] = ChatInviteLink(
        invite_link="https://t.me/+abc",
        creator=tg_user(1, is_bot=True),
        creates_join_request=False,
        is_primary=False,
        is_revoked=False,
    )
    from app.bot.handlers.clans import ClanCb

    await client.post(
        "/tg/webhook",
        json={
            "update_id": 4,
            "callback_query": {
                "id": "cb",
                "chat_instance": "ci",
                "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
                "data": ClanCb(action="subs", clan_id=clan.id).pack(),
            },
        },
        headers=WEBHOOK,
    )
    await db.refresh(clan)
    assert clan.invite_link == "https://t.me/+abc"
    assert (await db.get(User, 1)) is None  # bot flow does not create players
