from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user, get_user_locked, limit
from app.bot.instance import get_bot
from app.config import get_settings
from app.db import get_session
from app.game import player_service, shop_service
from app.game.errors import GameError
from app.game.shop_items import CLAN_PALETTE, ITEMS, ITEMS_BY_ID
from app.game.state import build_state
from app.i18n import pick_lang
from app.models import Clan, User, UserBoost

router = APIRouter()


@router.get("/shop")
async def shop(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    now = player_service.utcnow()
    admins = get_settings().admin_id_set
    clan = await session.get(Clan, user.clan_id) if user.clan_id else None
    is_owner = clan is not None and clan.kind != "militia" and clan.owner_user_id == user.id
    items = []
    for item in ITEMS:
        if item.admin_only and user.id not in admins:
            continue
        used = await shop_service.uses_today(session, user.id, item.id, now.date())
        available = (item.daily_limit is None or used < item.daily_limit) and (
            not item.clan_owner_only or is_owner
        )
        items.append(
            {
                "id": item.id,
                "stars": item.stars,
                "daily_limit": item.daily_limit,
                "used_today": used,
                "param": item.param,
                "subscription": item.subscription,
                "clan_owner_only": item.clan_owner_only,
                "available": available,
            }
        )
    vip_active = player_service.is_vip(user, now)
    vip_shield = await session.get(UserBoost, (user.id, "vip_shield"))
    return {
        "items": items,
        "palette": CLAN_PALETTE,
        "coins_bag_amount": shop_service.coins_bag_amount(user),
        "is_clan_owner": is_owner,
        "vip_shield_available": vip_active
        and (vip_shield is None or vip_shield.uses_date != now.date()),
    }


class InvoiceIn(BaseModel):
    item_id: str = Field(max_length=32)
    param: str | None = Field(default=None, max_length=32)


@router.post("/shop/invoice", dependencies=[Depends(limit("invoice", 20, 60))])
async def invoice(
    body: InvoiceIn,
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    link = await shop_service.create_invoice(
        session, get_bot(), user, body.item_id, body.param, pick_lang(user.language_code)
    )
    return {"invoice_link": link, "stars": ITEMS_BY_ID[body.item_id].stars}


class ShieldIn(BaseModel):
    h3: str = Field(max_length=16)


@router.post("/shop/vip_shield", dependencies=[Depends(limit("vip_shield", 10, 60))])
async def vip_shield(
    body: ShieldIn,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    if not player_service.is_vip(user, now):
        raise GameError("vip_required", 403)
    boost = await session.get(UserBoost, (user.id, "vip_shield"), with_for_update=True)
    if boost is not None and boost.uses_date == now.date():
        raise GameError("daily_limit", 409)
    sector = await shop_service.apply_shield(session, user, body.h3, now)
    if boost is None:
        session.add(
            UserBoost(user_id=user.id, boost_id="vip_shield", uses_today=1, uses_date=now.date())
        )
    else:
        boost.uses_today, boost.uses_date = 1, now.date()
    state = await build_state(session, user, now)
    await session.commit()
    return {"shield_until": sector.shield_until.isoformat(), "state": state}
