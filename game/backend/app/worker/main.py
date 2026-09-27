"""Background worker: scheduled jobs and the notification sender.

Run exactly one instance: python -m app.worker.main
"""

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.instance import get_bot
from app.config import get_settings
from app.worker import jobs
from app.worker.notifications import Sender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")


def heartbeat() -> None:
    log.info("worker alive")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(heartbeat, "interval", minutes=10, id="heartbeat")
    scheduler.add_job(jobs.hourly_control_points, "cron", minute=0, id="control_points")
    scheduler.add_job(jobs.season_check, "interval", minutes=5, id="season_check")
    scheduler.add_job(jobs.cleanup_battle_log, "cron", hour=3, minute=15, id="battle_log_cleanup")
    scheduler.add_job(jobs.notify_sector_losses, "cron", minute="*/30", id="notify_losses")
    scheduler.add_job(jobs.notify_group_digests, "cron", hour="*/3", minute=5, id="notify_digests")
    scheduler.add_job(jobs.notify_storage_full, "cron", minute=20, id="notify_storage")
    scheduler.add_job(
        jobs.notify_weekly_results, "cron", day_of_week="mon", hour=12, minute=10, id="weekly"
    )
    scheduler.add_job(jobs.hourly_map_snapshot, "cron", minute=2, id="map_snapshot")
    return scheduler


async def wait_for_database(attempts: int = 60, delay: float = 3.0) -> None:
    """The API container runs migrations on start; wait until the schema is there."""
    for attempt in range(1, attempts + 1):
        try:
            await jobs.season_check()  # also makes sure a season exists
            return
        except Exception as exc:  # noqa: BLE001 - any DB error means "not ready yet"
            log.info("database not ready (%s/%s): %s", attempt, attempts, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("database is not ready")


async def main() -> None:
    get_settings()
    await wait_for_database()
    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker started")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    sender = asyncio.create_task(Sender(get_bot()).run(stop))
    await stop.wait()
    scheduler.shutdown(wait=False)
    await sender
    await get_bot().session.close()
    log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
