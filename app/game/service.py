"""Game logic: claiming words, battles, captures, shields, buyouts, and leaderboards.

Every balance change and ownership transfer is an atomic UPDATE with a condition, so parallel requests
never cause double spending or a word "splitting" between two owners.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.database import Database
from app.db.models import Auction, Battle, Card, Offer, User
from app.game import rules
from app.game.battle import BattleResult, Fighter, simulate, tell_story
from app.game.genesis import NotAllowed, invent_creature
from app.game.render import CardView, render_card
from app.game.words import is_reserved
from app.services.images import ImageBackend, build_request
from app.services.llm import LLMClient
from app.services.queue import PRIORITY_FREE, PRIORITY_PREMIUM, GenerationQueue
from app.utils import local_today, utcnow

log = logging.getLogger(__name__)

ART_STYLE = (
    "fantasy trading card illustration, single creature, centered composition, dramatic lighting, "
    "vivid colors, highly detailed digital painting"
)
REDRAW_PRICE = 20
STALE_CREATING = timedelta(minutes=15)

Daily = Literal["quill", "battle"]


class GameError(Exception):
    """An error with a meaning for the player. ``code`` is used to pick the message text."""

    def __init__(self, code: str, **data: object) -> None:
        super().__init__(code)
        self.code = code
        self.data = data


class NotEnoughCrystals(GameError):
    def __init__(self, need: int) -> None:
        super().__init__("no_crystals", need=need)
        self.need = need


@dataclass(frozen=True)
class Spend:
    kind: Daily
    how: str  # free | paid
    price: int = 0


@dataclass
class Lookup:
    word: str
    card: Card | None = None
    reserved: bool = False
    creating: bool = False


@dataclass
class Created:
    card: Card
    image: bytes


@dataclass
class BattleOutcome:
    capture: bool
    attacker: Card
    defender: Card
    result: BattleResult
    story: str
    attacker_user_id: int
    defender_user_id: int
    rating_delta: int
    xp_gain: int
    level_up: bool
    captured: bool = False
    stake: int = 0
    payout: int = 0
    spend: Spend | None = None


@dataclass
class OfferResult:
    offer: Offer
    card: Card | None
    ok: bool
    payout: int = 0
    canceled: list[Offer] | None = None


def is_lord(user: User, now: datetime | None = None) -> bool:
    return bool(user.premium_until and user.premium_until > (now or utcnow()))


def public_name(user: User | None) -> str:
    if user is None:
        return "Неизвестный"
    name = " ".join((user.first_name or "").split())
    return name[:24] if name else f"Игрок {user.id % 100000}"


def fighter(card: Card) -> Fighter:
    return Fighter(
        name=card.name,
        word=card.display,
        element=card.element,
        klass=card.klass,
        atk=card.atk,
        def_=card.def_,
        hp=card.hp,
        level=card.level,
        ability=card.ability,
    )


def protection_until(card: Card) -> datetime | None:
    moments = [m for m in (card.protected_until, card.shield_until) if m]
    return max(moments) if moments else None


class GameService:
    def __init__(
        self, db: Database, settings: Settings, llm: LLMClient, images: ImageBackend, gen: GenerationQueue
    ) -> None:
        self.db = db
        self.settings = settings
        self.llm = llm
        self.images = images
        self.gen = gen

    # ---------- кошелёк и дневные лимиты ----------

    def daily_limit(self, kind: Daily, lord: bool) -> int:
        s = self.settings
        if kind == "quill":
            return s.lord_quills_per_day if lord else s.free_quills_per_day
        return s.lord_battles_per_day if lord else s.free_battles_per_day

    def daily_price(self, kind: Daily) -> int:
        return self.settings.quill_price if kind == "quill" else self.settings.battle_price

    def used_today(self, user: User) -> tuple[int, int]:
        if user.counters_date != local_today(self.settings.tz):
            return 0, 0
        return user.quills_today or 0, user.battles_today or 0

    @staticmethod
    async def spend_crystals(s: AsyncSession, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return True
        result = await s.execute(
            update(User).where(User.id == user_id, User.crystals >= amount).values(crystals=User.crystals - amount)
        )
        return result.rowcount == 1

    @staticmethod
    async def add_crystals(s: AsyncSession, user_id: int, amount: int) -> None:
        if amount:
            await s.execute(update(User).where(User.id == user_id).values(crystals=User.crystals + amount))

    async def _is_lord(self, s: AsyncSession, user_id: int) -> bool:
        until = await s.scalar(select(User.premium_until).where(User.id == user_id))
        return bool(until and until > utcnow())

    async def fee_percent(self, s: AsyncSession, user_id: int) -> int:
        lord = await self._is_lord(s, user_id)
        return self.settings.lord_fee_percent if lord else self.settings.fee_percent

    async def spend_daily(self, s: AsyncSession, user_id: int, kind: Daily) -> Spend | None:
        today = local_today(self.settings.tz)
        await s.execute(
            update(User)
            .where(User.id == user_id, or_(User.counters_date.is_(None), User.counters_date != today))
            .values(quills_today=0, battles_today=0, counters_date=today)
        )
        limit = self.daily_limit(kind, await self._is_lord(s, user_id))
        counter = User.quills_today if kind == "quill" else User.battles_today
        result = await s.execute(
            update(User).where(User.id == user_id, counter < limit).values({counter: counter + 1})
        )
        if result.rowcount == 1:
            return Spend(kind, "free")
        price = self.daily_price(kind)
        if await self.spend_crystals(s, user_id, price):
            return Spend(kind, "paid", price)
        return None

    async def refund_daily(self, s: AsyncSession, user_id: int, spend: Spend) -> None:
        if spend.how == "paid":
            await self.add_crystals(s, user_id, spend.price)
            return
        counter = User.quills_today if spend.kind == "quill" else User.battles_today
        await s.execute(
            update(User).where(User.id == user_id).values({counter: case((counter > 0, counter - 1), else_=0)})
        )

    # ---------- слова ----------

    @staticmethod
    async def _on_auction(s: AsyncSession, word: str) -> bool:
        return bool(await s.scalar(select(Auction.id).where(Auction.word == word, Auction.status == "active")))

    async def lookup(self, word: str) -> Lookup:
        async with self.db.session() as s:
            card = await s.scalar(select(Card).where(Card.word == word))
            on_auction = card is None and await self._on_auction(s, word)
        if card is not None:
            return Lookup(word, card) if card.status == "active" else Lookup(word, creating=True)
        return Lookup(word, reserved=is_reserved(word) or on_auction)

    async def get_card(self, card_id: int) -> Card | None:
        async with self.db.session() as s:
            card = await s.get(Card, card_id, populate_existing=True)
        return card if card and card.status == "active" else None

    async def reserve(self, user_id: int, word: str, display: str) -> tuple[int, Spend]:
        """Claim the word before generation starts: whoever is first owns it. The quill is charged right away."""
        if is_reserved(word):
            raise GameError("reserved")
        now = utcnow()
        try:
            async with self.db.begin() as s:
                owner = await s.scalar(select(Card.owner_id).where(Card.word == word))
                if owner is not None:
                    raise GameError("mine" if owner == user_id else "taken")
                if await self._on_auction(s, word):
                    raise GameError("reserved")
                spend = await self.spend_daily(s, user_id, "quill")
                if spend is None:
                    raise NotEnoughCrystals(self.settings.quill_price)
                card = Card(
                    word=word,
                    display=display,
                    status="creating",
                    owner_id=user_id,
                    creator_id=user_id,
                    created_at=now,
                    owned_since=now,
                )
                s.add(card)
                await s.flush()
                return card.id, spend
        except IntegrityError as e:
            raise GameError("taken") from e

    async def reserve_for_auction(self, user_id: int, word: str, display: str) -> int:
        now = utcnow()
        async with self.db.begin() as s:
            card = Card(
                word=word, display=display, status="creating", owner_id=user_id, creator_id=user_id,
                created_at=now, owned_since=now,
            )
            s.add(card)
            await s.flush()
            return card.id

    async def _drop_reservation(self, card_id: int, owner_id: int, spend: Spend | None) -> None:
        async with self.db.begin() as s:
            await s.execute(delete(Card).where(Card.id == card_id, Card.status == "creating"))
            if spend:
                await self.refund_daily(s, owner_id, spend)

    async def draw_art(self, prompt: str, lord: bool) -> bytes | None:
        req = build_request(self.settings, f"{prompt}, {ART_STYLE}", "auto", "3x2")  # под окно арта на карте
        priority = PRIORITY_PREMIUM if lord else PRIORITY_FREE
        try:
            return await self.gen.submit(lambda: self.images.generate(req), priority)
        except Exception as e:  # noqa: BLE001 — без арта карта всё равно создаётся, его можно дорисовать
            log.warning("Art generation failed: %r", e)
            return None

    async def _creator_name(self, s: AsyncSession, card: Card) -> str:
        return public_name(await s.get(User, card.creator_id))

    def _view(self, card: Card, creator: str, bot_username: str) -> CardView:
        return CardView(
            word=card.display,
            name=card.name,
            title=card.title,
            element=card.element,
            klass=card.klass,
            rarity=card.rarity,
            atk=card.atk,
            def_=card.def_,
            hp=card.hp,
            ability=card.ability,
            ability_text=card.ability_text,
            number=card.id,
            creator=creator,
            bot_username=bot_username,
        )

    async def create_card(
        self,
        card_id: int,
        spend: Spend | None,
        lord: bool,
        bot_username: str = "",
        rarities: list[str] | None = None,
    ) -> Created:
        """Invent a creature, draw the art, and render the card. On error, the reservation is dropped and the quill refunded."""
        async with self.db.session() as s:
            card = await s.get(Card, card_id)
            assert card is not None
            creator = await self._creator_name(s, card)
        try:
            draft = await invent_creature(self.llm, card.word)
        except NotAllowed as e:
            await self._drop_reservation(card_id, card.owner_id, spend)
            raise GameError("forbidden", reason=e.reason) from e

        try:
            rng = random.Random()
            rarity = rules.roll_rarity(rng, lord, rarities)
            atk, def_, hp = rules.make_stats(draft.atk, draft.def_, draft.hp, rarity, rng)
            art = await self.draw_art(draft.art, lord)
            now = utcnow()
            async with self.db.begin() as s:
                await s.execute(
                    update(Card)
                    .where(Card.id == card_id)
                    .values(
                        status="active",
                        name=draft.name,
                        title=draft.title,
                        element=draft.element,
                        klass=draft.klass,
                        rarity=rarity,
                        atk=atk,
                        def_=def_,
                        hp=hp,
                        ability=draft.ability,
                        ability_text=draft.ability_text,
                        lore=draft.lore,
                        art_prompt=draft.art,
                        has_art=art is not None,
                        value=rules.card_value(rarity, 1),
                        protected_until=now + timedelta(hours=self.settings.immunity_hours),
                        created_at=now,
                        owned_since=now,
                    )
                )
                await s.execute(
                    update(User).where(User.id == card.owner_id).values(words_created=User.words_created + 1)
                )
                fresh = await s.get(Card, card_id, populate_existing=True)
            assert fresh is not None
            image = await asyncio.to_thread(render_card, self._view(fresh, creator, bot_username), art)
            return Created(fresh, image)
        except Exception:
            log.exception("Card creation failed for %r", card.word)
            await self._drop_reservation(card_id, card.owner_id, spend)
            raise

    async def redraw(self, user_id: int, card_id: int, lord: bool, bot_username: str = "") -> Created:
        """Redraw the art: free if the card has no art (the GPU was off), otherwise for crystals."""
        async with self.db.begin() as s:
            card = await s.get(Card, card_id, populate_existing=True)
            if card is None or card.status != "active":
                raise GameError("not_found")
            if card.owner_id != user_id:
                raise GameError("not_owner")
            price = 0 if not card.has_art else REDRAW_PRICE
            if not await self.spend_crystals(s, user_id, price):
                raise NotEnoughCrystals(price)
            creator = await self._creator_name(s, card)
        art = await self.draw_art(card.art_prompt, lord)
        if art is None:
            async with self.db.begin() as s:
                await self.add_crystals(s, user_id, price)
            raise GameError("gpu_offline")
        async with self.db.begin() as s:
            await s.execute(update(Card).where(Card.id == card_id).values(has_art=True))
        card.has_art = True
        image = await asyncio.to_thread(render_card, self._view(card, creator, bot_username), art)
        return Created(card, image)

    async def set_file_id(self, card_id: int, file_id: str) -> None:
        async with self.db.begin() as s:
            await s.execute(update(Card).where(Card.id == card_id).values(file_id=file_id))

    async def cleanup_stale(self) -> None:
        """Delete reservations "stuck" due to a crash in the middle of generation."""
        async with self.db.begin() as s:
            await s.execute(
                delete(Card).where(Card.status == "creating", Card.created_at < utcnow() - STALE_CREATING)
            )

    # ---------- коллекция и топы ----------

    async def user_cards(self, user_id: int, offset: int = 0, limit: int = 8) -> tuple[list[Card], int, int]:
        """(cards on the page, total count, total value)"""
        async with self.db.session() as s:
            cards = (
                await s.scalars(
                    select(Card)
                    .where(Card.owner_id == user_id, Card.status == "active")
                    .order_by(Card.value.desc(), Card.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            count, total = (
                await s.execute(
                    select(func.count(Card.id), func.coalesce(func.sum(Card.value), 0)).where(
                        Card.owner_id == user_id, Card.status == "active"
                    )
                )
            ).one()
        return list(cards), int(count), int(total)

    async def top_lords(self, limit: int = 10) -> list[tuple[User, int, int]]:
        async with self.db.session() as s:
            total = func.sum(Card.value).label("total")
            rows = (
                await s.execute(
                    select(Card.owner_id, total, func.count(Card.id))
                    .where(Card.status == "active")
                    .group_by(Card.owner_id)
                    .order_by(total.desc())
                    .limit(limit)
                )
            ).all()
            users = {u.id: u for u in (await s.scalars(select(User).where(User.id.in_([r[0] for r in rows])))).all()}
        return [(users[r[0]], int(r[1]), int(r[2])) for r in rows if r[0] in users]

    async def top_cards(self, limit: int = 10) -> list[Card]:
        async with self.db.session() as s:
            return list(
                (
                    await s.scalars(
                        select(Card).where(Card.status == "active").order_by(Card.value.desc(), Card.wins.desc()).limit(limit)
                    )
                ).all()
            )

    async def top_fighters(self, limit: int = 10) -> list[User]:
        async with self.db.session() as s:
            return list(
                (
                    await s.scalars(
                        select(User).where(User.wins + User.losses > 0).order_by(User.rating.desc()).limit(limit)
                    )
                ).all()
            )

    async def world_size(self) -> int:
        async with self.db.session() as s:
            return int(await s.scalar(select(func.count(Card.id)).where(Card.status == "active")) or 0)

    async def search(self, prefix: str, limit: int = 10) -> list[Card]:
        async with self.db.session() as s:
            query = select(Card).where(Card.status == "active", Card.file_id.is_not(None))
            if prefix:
                query = query.where(Card.word.startswith(prefix, autoescape=True)).order_by(func.length(Card.word))
            else:
                query = query.order_by(Card.value.desc())
            return list((await s.scalars(query.limit(limit))).all())

    # ---------- бои ----------

    async def random_opponent(self, user_id: int, card: Card) -> Card | None:
        idx = rules.RARITY_ORDER.index(card.rarity)
        near = rules.RARITY_ORDER[max(0, idx - 1) : idx + 2]
        async with self.db.session() as s:
            base = select(Card).where(Card.status == "active", Card.owner_id != user_id)
            found = await s.scalar(base.where(Card.rarity.in_(near)).order_by(func.random()).limit(1))
            return found or await s.scalar(base.order_by(func.random()).limit(1))

    async def _add_xp(self, s: AsyncSession, card_id: int, xp: int, win: bool) -> bool:
        before = await s.scalar(select(Card.level).where(Card.id == card_id)) or 1
        await s.execute(
            update(Card)
            .where(Card.id == card_id)
            .values(xp=Card.xp + xp, wins=Card.wins + int(win), losses=Card.losses + int(not win))
        )
        total_xp, rarity = (await s.execute(select(Card.xp, Card.rarity).where(Card.id == card_id))).one()
        level = rules.level_for_xp(total_xp)
        await s.execute(
            update(Card).where(Card.id == card_id).values(level=level, value=rules.card_value(rarity, level))
        )
        return level > before

    async def battle(self, user_id: int, my_card_id: int, target_card_id: int, capture: bool) -> BattleOutcome:
        now = utcnow()
        async with self.db.session() as s:
            mine = await s.get(Card, my_card_id)
            target = await s.get(Card, target_card_id)
        if mine is None or target is None or mine.status != "active" or target.status != "active":
            raise GameError("not_found")
        if mine.owner_id != user_id:
            raise GameError("not_owner")
        if target.owner_id == user_id:
            raise GameError("own_card")
        defender_id = target.owner_id
        if capture and (until := protection_until(target)) and until > now:
            raise GameError("protected", until=until)

        result = simulate(fighter(mine), fighter(target), random.Random())
        won = result.attacker_won
        spend: Spend | None = None
        stake = payout = 0
        captured = False

        async with self.db.begin() as s:
            if capture:
                stake = target.value
                if not await self.spend_crystals(s, user_id, stake):
                    raise NotEnoughCrystals(stake)
                fresh_owner, prot, shield = (
                    await s.execute(
                        select(Card.owner_id, Card.protected_until, Card.shield_until).where(Card.id == target.id)
                    )
                ).one()
                if fresh_owner != defender_id or max(prot or now, shield or now) > now:
                    raise GameError("changed")
            else:
                spend = await self.spend_daily(s, user_id, "battle")
                if spend is None:
                    raise NotEnoughCrystals(self.settings.battle_price)

            xp_gain = 30 if won else 10
            level_up = await self._add_xp(s, mine.id, xp_gain, won)
            await self._add_xp(s, target.id, 5 if won else 20, not won)

            a_rating = await s.scalar(select(User.rating).where(User.id == user_id)) or 1000
            d_rating = await s.scalar(select(User.rating).where(User.id == defender_id)) or 1000
            delta = rules.elo(a_rating, d_rating) if won else rules.elo(d_rating, a_rating)
            sign = 1 if won else -1
            await s.execute(
                update(User)
                .where(User.id == user_id)
                .values(rating=User.rating + sign * delta, wins=User.wins + int(won), losses=User.losses + int(not won))
            )
            await s.execute(
                update(User)
                .where(User.id == defender_id)
                .values(rating=User.rating - sign * delta, wins=User.wins + int(not won), losses=User.losses + int(won))
            )

            if capture:
                payout = stake - stake * await self.fee_percent(s, defender_id) // 100
                await self.add_crystals(s, defender_id, payout)
                if won:
                    moved = await s.execute(
                        update(Card)
                        .where(Card.id == target.id, Card.owner_id == defender_id)
                        .values(
                            owner_id=user_id,
                            owned_since=now,
                            protected_until=now + timedelta(hours=self.settings.immunity_hours),
                            shield_until=None,
                        )
                    )
                    captured = moved.rowcount == 1
                    if captured:
                        await self._cancel_offers(s, target.id)

            s.add(
                Battle(
                    kind="capture" if capture else "friendly",
                    attacker_id=user_id,
                    defender_id=defender_id,
                    attacker_card_id=mine.id,
                    defender_card_id=target.id,
                    attacker_won=won,
                    stake=stake,
                    created_at=now,
                )
            )

        story = await tell_story(self.llm, fighter(mine), fighter(target), result)
        async with self.db.session() as s:
            attacker = await s.get(Card, mine.id, populate_existing=True)
            defender = await s.get(Card, target.id, populate_existing=True)
        assert attacker is not None and defender is not None
        return BattleOutcome(
            capture=capture,
            attacker=attacker,
            defender=defender,
            result=result,
            story=story,
            attacker_user_id=user_id,
            defender_user_id=defender_id,
            rating_delta=delta,
            xp_gain=xp_gain,
            level_up=level_up,
            captured=captured,
            stake=stake,
            payout=payout,
            spend=spend,
        )

    # ---------- щиты ----------

    def shield_price(self, card: Card) -> int:
        return max(5, card.value * self.settings.shield_percent // 100)

    async def buy_shield(self, user_id: int, card_id: int) -> datetime:
        now = utcnow()
        async with self.db.begin() as s:
            card = await s.get(Card, card_id, populate_existing=True)
            if card is None or card.status != "active":
                raise GameError("not_found")
            if card.owner_id != user_id:
                raise GameError("not_owner")
            price = self.shield_price(card)
            if not await self.spend_crystals(s, user_id, price):
                raise NotEnoughCrystals(price)
            base = max(now, card.shield_until or now)
            until = base + timedelta(days=self.settings.shield_days)
            await s.execute(update(Card).where(Card.id == card_id).values(shield_until=until))
            return until

    # ---------- выкуп ----------

    async def _cancel_offers(self, s: AsyncSession, card_id: int, keep_id: int | None = None) -> list[Offer]:
        query = select(Offer).where(Offer.card_id == card_id, Offer.status == "pending")
        if keep_id is not None:
            query = query.where(Offer.id != keep_id)
        offers = list((await s.scalars(query)).all())
        for offer in offers:
            result = await s.execute(
                update(Offer).where(Offer.id == offer.id, Offer.status == "pending").values(status="canceled")
            )
            if result.rowcount == 1:
                await self.add_crystals(s, offer.buyer_id, offer.price)
        return offers

    async def make_offer(self, buyer_id: int, card_id: int, price: int) -> Offer:
        if price < 1:
            raise GameError("bad_price")
        async with self.db.begin() as s:
            card = await s.get(Card, card_id, populate_existing=True)
            if card is None or card.status != "active":
                raise GameError("not_found")
            if card.owner_id == buyer_id:
                raise GameError("own_card")
            exists = await s.scalar(
                select(Offer.id).where(Offer.card_id == card_id, Offer.buyer_id == buyer_id, Offer.status == "pending")
            )
            if exists:
                raise GameError("offer_exists")
            if not await self.spend_crystals(s, buyer_id, price):
                raise NotEnoughCrystals(price)
            offer = Offer(
                card_id=card_id, buyer_id=buyer_id, seller_id=card.owner_id, price=price,
                status="pending", created_at=utcnow(),
            )
            s.add(offer)
            await s.flush()
            return offer

    async def accept_offer(self, seller_id: int, offer_id: int) -> OfferResult:
        now = utcnow()
        async with self.db.begin() as s:
            accepted = await s.execute(
                update(Offer)
                .where(Offer.id == offer_id, Offer.seller_id == seller_id, Offer.status == "pending")
                .values(status="accepted")
            )
            offer = await s.get(Offer, offer_id, populate_existing=True)
            if accepted.rowcount != 1 or offer is None:
                raise GameError("offer_gone")
            moved = await s.execute(
                update(Card)
                .where(Card.id == offer.card_id, Card.owner_id == seller_id, Card.status == "active")
                .values(
                    owner_id=offer.buyer_id,
                    owned_since=now,
                    protected_until=now + timedelta(hours=self.settings.immunity_hours),
                    shield_until=None,
                )
            )
            if moved.rowcount != 1:
                await s.execute(update(Offer).where(Offer.id == offer_id).values(status="canceled"))
                await self.add_crystals(s, offer.buyer_id, offer.price)
                return OfferResult(offer, None, ok=False)
            payout = offer.price - offer.price * await self.fee_percent(s, seller_id) // 100
            await self.add_crystals(s, seller_id, payout)
            canceled = await self._cancel_offers(s, offer.card_id, keep_id=offer_id)
            card = await s.get(Card, offer.card_id, populate_existing=True)
        return OfferResult(offer, card, ok=True, payout=payout, canceled=canceled)

    async def decline_offer(self, seller_id: int, offer_id: int) -> Offer:
        async with self.db.begin() as s:
            declined = await s.execute(
                update(Offer)
                .where(Offer.id == offer_id, Offer.seller_id == seller_id, Offer.status == "pending")
                .values(status="declined")
            )
            offer = await s.get(Offer, offer_id, populate_existing=True)
            if declined.rowcount != 1 or offer is None:
                raise GameError("offer_gone")
            await self.add_crystals(s, offer.buyer_id, offer.price)
            return offer

    async def expire_offers(self) -> list[Offer]:
        threshold = utcnow() - timedelta(hours=self.settings.offer_ttl_hours)
        expired: list[Offer] = []
        async with self.db.begin() as s:
            offers = (
                await s.scalars(select(Offer).where(Offer.status == "pending", Offer.created_at < threshold))
            ).all()
            for offer in offers:
                result = await s.execute(
                    update(Offer).where(Offer.id == offer.id, Offer.status == "pending").values(status="expired")
                )
                if result.rowcount == 1:
                    await self.add_crystals(s, offer.buyer_id, offer.price)
                    expired.append(offer)
        return expired
