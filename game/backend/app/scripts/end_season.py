"""Finish the current season by hand.

    python -m app.scripts.end_season --dry-run          # show winners, change nothing
    python -m app.scripts.end_season --apply            # only if the season is over
    python -m app.scripts.end_season --apply --force    # finish right now

The worker runs the same code automatically every 5 minutes.
"""

import argparse
import asyncio
import json

from app.db import dispose_engine, get_sessionmaker
from app.game import player_service, season_service


async def run(apply: bool, force: bool) -> None:
    async with get_sessionmaker()() as session:
        now = player_service.utcnow()
        await season_service.ensure_active_season(session, now)
        results = await season_service.end_season(session, now, apply=apply, force=force)
        if apply:
            await session.commit()
        else:
            await session.rollback()
    await dispose_engine()
    if results is None:
        print("Nothing to do: the active season is not over yet (use --force).")
        return
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("APPLIED" if apply else "DRY RUN: nothing was changed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true", help="finish before ends_at")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, force=args.force or args.dry_run))


if __name__ == "__main__":
    main()
