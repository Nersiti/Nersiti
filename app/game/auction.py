"""Daily auction of "hot" words (love, money, Friday…): crystals are burned — the main sink of the economy."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select, update

from app.config import Settings
from app.db.database import Database
from app.db.models import Auction, Card, User
from app.game.service import GameError, GameService, NotEnoughCrystals
from app.game.words import display_form, reserved_words
from app.utils import local_today, utcnow

log = logging.getLogger(__name__)

AUCTION_RARITIES = ["legendary", "mythic"]


@dataclass
class BidResult:
    auction: Auction
    outbid_user_id: int | None
    outbid_amount: int


def min_next_bid(auction: Auction, settings: Settings) -> int:
    if auction.top_bid <= 0:
        return settings.auction_min_bid
    step = max(10, auction.top_bid * settings.auction_step_percent // 100)
    return auction.top_bid + step


class AuctionService:
    def __init__(self, db: Database, settings: Settings, game: GameService) -> None:
        self.db = db
        self.settings = settings
        self.game = game

    async def current(self) -> Auction | None:
        async with self.db.session() as s:
            return await s.scalar(
                select(Auction).where(Auction.status == "active").order_by(Auction.ends_at).limit(1)
            )

    async def get(self, auction_id: int) -> Auction | None:
        async with self.db.session() as s:
            return await s.get(Auction, auction_id, populate_existing=True)

    async def start(self, word: str, ends_at: datetime, display: str | None = None) -> Auction:
        async with self.db.begin() as s:
            if await s.scalar(select(Card.id).where(Card.word == word)):
                raise GameError("taken")
            if await s.scalar(select(Auction.id).where(Auction.word == word, Auction.status == "active")):
                raise GameError("auction_exists")
            auction = Auction(
                word=word,
                display=display or display_form(word),
                status="active",
                starts_at=utcnow(),
                ends_at=ends_at,
            )
            s.add(auction)
            await s.flush()
            return auction

    async def bid(self, user_id: int, auction_id: int, amount: int) -> BidResult:
        now = utcnow()
        async with self.db.begin() as s:
            auction = await s.get(Auction, auction_id, populate_existing=True)
            if auction is None or auction.status != "active" or auction.ends_at <= now:
                raise GameError("auction_closed")
            if auction.top_bidder_id == user_id:
                raise GameError("already_top")
            need = min_next_bid(auction, self.settings)
            if amount < need:
                raise GameError("bid_too_low", need=need)
            if not await self.game.spend_crystals(s, user_id, amount):
                raise NotEnoughCrystals(amount)

            snipe = timedelta(minutes=self.settings.auction_snipe_minutes)
            new_end = max(auction.ends_at, now + snipe)
            prev_user, prev_amount = auction.top_bidder_id, auction.top_bid
            updated = await s.execute(
                update(Auction)
                .where(Auction.id == auction_id, Auction.status == "active", Auction.top_bid == prev_amount)
                .values(
                    top_bid=amount,
                    top_bidder_id=user_id,
                    bids_count=Auction.bids_count + 1,
                    ends_at=new_end,
                )
            )
            if updated.rowcount != 1:
                raise GameError("bid_race")
            if prev_user:
                await self.game.add_crystals(s, prev_user, prev_amount)
            fresh = await s.get(Auction, auction_id, populate_existing=True)
            assert fresh is not None
        return BidResult(fresh, prev_user, prev_amount)

    async def close_due(self) -> list[Auction]:
        """Close finished auctions. Returns those that have a winner (the card still needs to be created)."""
        now = utcnow()
        won: list[Auction] = []
        async with self.db.begin() as s:
            due = (
                await s.scalars(select(Auction).where(Auction.status == "active", Auction.ends_at <= now))
            ).all()
            for auction in due:
                status = "finished" if auction.top_bidder_id else "empty"
                result = await s.execute(
                    update(Auction).where(Auction.id == auction.id, Auction.status == "active").values(status=status)
                )
                if result.rowcount == 1 and auction.top_bidder_id:
                    auction.status = status
                    won.append(auction)
        return won

    async def refund_winner(self, auction: Auction) -> bool:
        """The word went to someone else (e.g. claimed before the auction) — return the winning bid."""
        async with self.db.begin() as s:
            result = await s.execute(
                update(Auction)
                .where(Auction.id == auction.id, Auction.status == "finished", Auction.card_id.is_(None))
                .values(status="refunded")
            )
            if result.rowcount != 1 or not auction.top_bidder_id:
                return False
            await self.game.add_crystals(s, auction.top_bidder_id, auction.top_bid)
            return True

    async def attach_card(self, auction_id: int, card_id: int) -> None:
        async with self.db.begin() as s:
            await s.execute(update(Auction).where(Auction.id == auction_id).values(card_id=card_id))

    def _window(self) -> tuple[datetime, datetime]:
        """Today's auction start and end times (naive UTC)."""
        tz = self.settings.tz
        today = local_today(tz)

        def at(hour: int) -> datetime:
            return datetime.combine(today, time(hour % 24), tzinfo=tz).astimezone(UTC).replace(tzinfo=None)

        start, end = at(self.settings.auction_start_hour), at(self.settings.auction_end_hour)
        if end <= start:  # например, с 12:00 до 00:00 — торги заканчиваются на следующий день
            end += timedelta(days=1)
        return start, end

    async def pick_word(self) -> str | None:
        async with self.db.session() as s:
            taken = set((await s.scalars(select(Card.word))).all())
            busy = set(
                (await s.scalars(select(Auction.word).where(Auction.status.in_(("active", "finished"))))).all()
            )
        free = [w for w in reserved_words() if w not in taken and w not in busy]
        return random.choice(free) if free else None

    async def maybe_start_daily(self) -> Auction | None:
        if not self.settings.auction_enabled:
            return None
        start, end = self._window()
        now = utcnow()
        if not (start <= now < end):
            return None
        async with self.db.session() as s:
            if await s.scalar(select(Auction.id).where(Auction.status == "active")):
                return None
            if await s.scalar(select(Auction.id).where(Auction.starts_at >= start)):
                return None  # сегодняшний аукцион уже был
        word = await self.pick_word()
        if word is None:
            return None
        return await self.start(word, end)

    async def winner(self, auction: Auction) -> User | None:
        if not auction.top_bidder_id:
            return None
        async with self.db.session() as s:
            return await s.get(User, auction.top_bidder_id)
