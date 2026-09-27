import hmac
import logging
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from app.api import build_api_router
from app.bot.instance import get_bot, get_dispatcher
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.game.errors import GameError
from app.redis_client import close_redis, get_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast on bad config
    yield
    await get_bot().session.close()
    await close_redis()
    await dispose_engine()


app = FastAPI(title="World Battle", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(build_api_router(), prefix="/api")


@app.exception_handler(GameError)
async def game_error_handler(request: Request, exc: GameError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.code})


@app.get("/api/health")
async def health() -> dict:
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    await get_redis().ping()
    return {"ok": True}


@app.post("/tg/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    expected = get_settings().webhook_secret
    if not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
        raise HTTPException(status_code=403)
    bot = get_bot()
    # Never return 5xx to Telegram: it would re-deliver the update forever.
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
    except ValidationError:
        log.exception("Unparsable update")
        return {"ok": False}
    try:
        await get_dispatcher().feed_update(bot, update)
    except Exception:
        log.exception("Failed to process update %s", update.update_id)
    return {"ok": True}
