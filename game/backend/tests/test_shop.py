from datetime import UTC, datetime, timedelta

import h3
import pytest
from sqlalchemy import select, update

from app.game import player_service
from app.models import Clan, Payment, Sector, User, UserBoost
from tests.helpers import auth, login, seed_world

T0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
KAZAN_CENTER = h3.latlng_to_cell(55.78874, 49.12214, 6)
WEBHOOK = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(player_service, "utcnow", lambda: T0)


def tg_from(user_id: int) -> dict:
    return {"id": user_id, "is_bot": False, "first_name": "Buyer", "language_code": "ru"}


def pre_checkout(user_id: int, payload: str, amount: int) -> dict:
    return {
        "update_id": 10,
        "pre_checkout_query": {
            "id": "q1",
            "from": tg_from(user_id),
            "currency": "XTR",
            "total_amount": amount,
            "invoice_payload": payload,
        },
    }


def paid(
    user_id: int, payload: str, amount: int, charge: str, expiration: int | None = None
) -> dict:
    sp = {
        "currency": "XTR",
        "total_amount": amount,
        "invoice_payload": payload,
        "telegram_payment_charge_id": charge,
        "provider_payment_charge_id": "",
    }
    if expiration:
        sp["subscription_expiration_date"] = expiration
    return {
        "update_id": 11,
        "message": {
            "message_id": 5,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": tg_from(user_id),
            "successful_payment": sp,
        },
    }


async def onboard(client, db, user_id, city_id):
    await login(client, user_id)
    await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": city_id}, headers=auth(user_id)
    )


async def test_shop_listing_hides_admin_items(client, db):
    await login(client, 1)
    await login(client, 999)
    ids = [i["id"] for i in (await client.get("/api/shop", headers=auth(1))).json()["items"]]
    assert "test_star" not in ids and "vip" in ids
    ids = [i["id"] for i in (await client.get("/api/shop", headers=auth(999))).json()["items"]]
    assert "test_star" in ids


async def test_invoice_creation(client, db, bot_session):
    bot_session.responses["CreateInvoiceLink"] = "https://t.me/$invoice"
    await login(client, 1)
    res = await client.post("/api/shop/invoice", json={"item_id": "coins_bag"}, headers=auth(1))
    assert res.json() == {"invoice_link": "https://t.me/$invoice", "stars": 50}
    [call] = bot_session.of_type("CreateInvoiceLink")
    assert call.currency == "XTR"
    assert call.payload == "coins_bag|1|"
    assert call.prices[0].amount == 50
    assert call.subscription_period is None

    await client.post("/api/shop/invoice", json={"item_id": "vip"}, headers=auth(1))
    assert bot_session.of_type("CreateInvoiceLink")[-1].subscription_period == 2_592_000


async def test_invoice_validation(client, db, bot_session):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    db.add(UserBoost(user_id=1, boost_id="coins_bag", uses_today=5, uses_date=T0.date()))
    await db.commit()

    async def invoice(item_id, param=None):
        return await client.post(
            "/api/shop/invoice", json={"item_id": item_id, "param": param}, headers=auth(1)
        )

    assert (await invoice("coins_bag")).json()["detail"] == "daily_limit"
    assert (await invoice("clan_promo")).json()["detail"] == "not_clan_owner"
    assert (await invoice("shield", KAZAN_CENTER)).json()["detail"] == "sector_not_owned"
    assert (await invoice("shield")).json()["detail"] == "bad_param"
    assert (await invoice("test_star")).status_code == 404
    assert (await invoice("nope")).status_code == 404
    assert bot_session.of_type("CreateInvoiceLink") == []


async def test_pre_checkout_validates(client, bot_session):
    await login(client, 1)
    await client.post("/tg/webhook", json=pre_checkout(1, "coins_bag|1|", 50), headers=WEBHOOK)
    await client.post("/tg/webhook", json=pre_checkout(1, "coins_bag|1|", 1), headers=WEBHOOK)
    await client.post("/tg/webhook", json=pre_checkout(1, "coins_bag|2|", 50), headers=WEBHOOK)
    await client.post("/tg/webhook", json=pre_checkout(1, "garbage", 50), headers=WEBHOOK)
    answers = [a.ok for a in bot_session.of_type("AnswerPreCheckoutQuery")]
    assert answers == [True, False, False, False]


async def test_payment_granted_exactly_once(client, db, bot_session):
    await login(client, 1)
    update_ = paid(1, "coins_bag|1|", 50, "charge-1")
    await client.post("/tg/webhook", json=update_, headers=WEBHOOK)
    await client.post("/tg/webhook", json=update_, headers=WEBHOOK)  # Telegram re-delivery

    user = await db.get(User, 1)
    await db.refresh(user)
    assert user.coins == 1000 + 5000
    payments = (await db.execute(select(Payment))).scalars().all()
    assert len(payments) == 1 and payments[0].stars == 50
    assert len(bot_session.of_type("SendMessage")) == 1
    boost = await db.get(UserBoost, (1, "coins_bag"))
    assert boost.uses_today == 1


async def test_vip_subscription_and_renewal(client, db, bot_session):
    await login(client, 1)
    exp = int((T0 + timedelta(days=30)).timestamp())
    await client.post("/tg/webhook", json=paid(1, "vip|1|", 250, "sub-1", exp), headers=WEBHOOK)
    user = await db.get(User, 1)
    await db.refresh(user)
    assert user.vip_until == T0 + timedelta(days=30)

    exp2 = int((T0 + timedelta(days=60)).timestamp())
    await client.post("/tg/webhook", json=paid(1, "vip|1|", 250, "sub-2", exp2), headers=WEBHOOK)
    await db.refresh(user)
    assert user.vip_until == T0 + timedelta(days=60)
    state = (await login(client, 1))["state"]
    assert state["offline_cap_hours"] == 12


async def test_shield_purchase_and_limit(client, db, bot_session):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    clan_id = (await db.get(User, 1)).clan_id
    sectors = (
        (await db.execute(select(Sector).where(Sector.city_id == ids["kazan"]).limit(5)))
        .scalars()
        .all()
    )
    for s in sectors:
        s.owner_clan_id = clan_id
        s.defense = 1000
    await db.commit()

    first, second = sectors[0].h3, sectors[1].h3
    await client.post(
        "/tg/webhook", json=paid(1, f"shield|1|{first}", 100, "sh-1"), headers=WEBHOOK
    )
    sector = await db.get(Sector, first)
    await db.refresh(sector)
    assert sector.shield_until == T0 + timedelta(hours=8)

    # 5 sectors -> at most max(1, 10%) = 1 shield at a time.
    res = await client.post(
        "/api/shop/invoice", json={"item_id": "shield", "param": second}, headers=auth(1)
    )
    assert res.json()["detail"] == "shield_limit"


async def test_clan_owner_items(client, db, bot_session):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    clan = Clan(kind="channel", tg_chat_id=-9, title="Мой", color="#000000", owner_user_id=1)
    db.add(clan)
    await db.commit()
    await db.execute(update(User).where(User.id == 1).values(clan_id=clan.id))
    await db.commit()

    await client.post(
        "/tg/webhook", json=paid(1, "clan_color|1|#22c55e", 300, "c-1"), headers=WEBHOOK
    )
    await client.post("/tg/webhook", json=paid(1, "clan_promo|1|", 500, "c-2"), headers=WEBHOOK)
    await db.refresh(clan)
    assert clan.color == "#22c55e"
    assert clan.promoted_until == T0 + timedelta(hours=24)
    top = (await client.get("/api/clans/top", headers=auth(1))).json()
    assert [c["id"] for c in top["promoted"]] == [clan.id]


async def test_vip_free_shield(client, db):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    user = await db.get(User, 1)
    await db.execute(
        update(Sector).where(Sector.h3 == KAZAN_CENTER).values(owner_clan_id=user.clan_id)
    )
    await db.commit()
    res = await client.post("/api/shop/vip_shield", json={"h3": KAZAN_CENTER}, headers=auth(1))
    assert res.json()["detail"] == "vip_required"
    await db.execute(update(User).where(User.id == 1).values(vip_until=T0 + timedelta(days=1)))
    await db.commit()
    res = await client.post("/api/shop/vip_shield", json={"h3": KAZAN_CENTER}, headers=auth(1))
    assert res.status_code == 200
    res = await client.post("/api/shop/vip_shield", json={"h3": KAZAN_CENTER}, headers=auth(1))
    assert res.json()["detail"] == "daily_limit"


async def test_admin_refund(client, db, bot_session):
    await login(client, 1)
    exp = int((T0 + timedelta(days=30)).timestamp())
    await client.post("/tg/webhook", json=paid(1, "vip|1|", 250, "sub-9", exp), headers=WEBHOOK)

    def cmd(user_id: int, text: str) -> dict:
        return {
            "update_id": 20,
            "message": {
                "message_id": 9,
                "date": 1700000000,
                "chat": {"id": user_id, "type": "private"},
                "from": tg_from(user_id),
                "text": text,
                "entities": [{"type": "bot_command", "offset": 0, "length": 7}],
            },
        }

    await client.post("/tg/webhook", json=cmd(1, "/refund sub-9"), headers=WEBHOOK)
    assert bot_session.of_type("RefundStarPayment") == []  # not an admin

    await client.post("/tg/webhook", json=cmd(999, "/refund sub-9"), headers=WEBHOOK)
    [refund] = bot_session.of_type("RefundStarPayment")
    assert (refund.user_id, refund.telegram_payment_charge_id) == (1, "sub-9")
    payment = (await db.execute(select(Payment))).scalar_one()
    await db.refresh(payment)
    assert payment.status == "refunded"
    user = await db.get(User, 1)
    await db.refresh(user)
    assert user.vip_until == T0
