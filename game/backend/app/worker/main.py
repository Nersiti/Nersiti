"""Background worker: scheduled jobs and the notification sender.

Run exactly one instance: python -m app.worker.main
"""

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.worker import jobs

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
    return scheduler


async def main() -> None:
    get_settings()
    await jobs.season_check()  # make sure a season exists before players arrive
    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker started")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=False)
    log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
