import uuid
from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user, limit
from app.bot.instance import get_bot
from app.db import get_session
from app.game import share_service
from app.game.errors import GameError
from app.i18n import pick_lang, t
from app.models import User

router = APIRouter()


@router.get("/share/links")
async def share_links(
    kind: Literal["me", "clan"] = "me",
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    return {
        "story_url": share_service.image_url(user.id, kind, "story"),
        "post_url": share_service.image_url(user.id, kind, "post"),
        "link": await share_service.share_link(session, user, kind),
        "text": t(lang, f"share.{kind}.text"),
        "button": t(lang, "share.button"),
    }


class PrepareIn(BaseModel):
    kind: Literal["me", "clan"] = "me"


@router.post("/share/prepare", dependencies=[Depends(limit("share_prepare", 20, 60))])
async def prepare_message(
    body: PrepareIn,
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Bot API 8.0 savePreparedInlineMessage: the Mini App then calls shareMessage(id)."""
    lang = pick_lang(user.language_code)
    photo = share_service.image_url(user.id, body.kind, "post")
    link = await share_service.share_link(session, user, body.kind)
    prepared = await get_bot().save_prepared_inline_message(
        user_id=user.id,
        result=InlineQueryResultPhoto(
            id=uuid.uuid4().hex,
            photo_url=photo,
            thumbnail_url=photo,
            caption=t(lang, f"share.{body.kind}.text"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(lang, "share.button"), url=link)]]
            ),
        ),
        allow_user_chats=True,
        allow_group_chats=True,
        allow_channel_chats=True,
    )
    return {"id": prepared.id}


@router.get("/share/img/{name}")
async def share_image(name: str, session: AsyncSession = Depends(get_session)) -> Response:
    """Public (Telegram fetches it): the URL is signed, see share_service.image_url."""
    user_id, kind, fmt = share_service.parse_name(name)
    user = await session.get(User, user_id)
    if user is None or user.banned:
        raise GameError("not_found", 404)
    data = await share_service.render_cached(session, user, kind, fmt)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={share_service.CACHE_SECONDS}"},
    )
