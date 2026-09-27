"""Scheduled jobs (run by the single worker process)."""

import logging
from datetime import timedelta

from sqlalchemy import delete

from app.db import get_sessionmaker
from app.game import player_service, season_service
from app.models import BattleLog
from app.worker import notifications

log = logging.getLogger("worker.jobs")

BATTLE_LOG_RETENTION = timedelta(days=30)


async def hourly_control_points() -> None:
    now = player_service.utcnow()
    async with get_sessionmaker()() as session:
        accrued = await season_service.accrue_control_points(session, now)
        await season_service.recompute_all_controllers(session)
        await session.commit()
    log.info("control points accrued: %s", accrued)


async def season_check() -> None:
    now = player_service.utcnow()
    async with get_sessionmaker()() as session:
        await season_service.ensure_active_season(session, now)
        results = await season_service.end_season(session, now, apply=True)
        await session.commit()
    if results is not None:
        log.info("season %s finished", results["season"])


async def cleanup_battle_log() -> None:
    cutoff = player_service.utcnow() - BATTLE_LOG_RETENTION
    async with get_sessionmaker()() as session:
        result = await session.execute(delete(BattleLog).where(BattleLog.created_at < cutoff))
        await session.commit()
    log.info("battle_log rows deleted: %s", result.rowcount)


async def notify_sector_losses() -> None:
    async with get_sessionmaker()() as session:
        queued = await notifications.sector_loss_summary(session, player_service.utcnow())
    log.info("loss notifications queued: %s", queued)


async def notify_group_digests() -> None:
    async with get_sessionmaker()() as session:
        queued = await notifications.group_digests(session, player_service.utcnow())
    log.info("group digests queued: %s", queued)


async def notify_storage_full() -> None:
    async with get_sessionmaker()() as session:
        queued = await notifications.storage_full_reminders(session, player_service.utcnow())
    log.info("storage reminders queued: %s", queued)
