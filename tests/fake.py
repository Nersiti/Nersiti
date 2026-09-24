"""Fake Telegram Bot API: records every bot request and returns plausible responses."""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    CopyMessage,
    CreateInvoiceLink,
    EditMessageReplyMarkup,
    EditMessageText,
    GetChatMember,
    GetMe,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberLeft,
    ChatMemberMember,
    InlineQuery,
    Message,
    MessageId,
    PhotoSize,
    PreCheckoutQuery,
    SuccessfulPayment,
    Update,
    User,
)

BOT_USER = User(id=42, is_bot=True, first_name="Test Bot", username="test_bot")


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.member_status = "member"
        self.errors: dict[type, Exception] = {}
        self._ids = itertools.count(1000)

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.requests.append(method)
        if type(method) in self.errors:
            raise self.errors[type(method)]
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, GetChatMember):
            if self.member_status == "left":
                return ChatMemberLeft(user=User(id=method.user_id, is_bot=False, first_name="U"))
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="U"))
        if isinstance(method, CreateInvoiceLink):
            return "https://t.me/$test_invoice"
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self._ids))
        if isinstance(method, (EditMessageText, EditMessageReplyMarkup)):
            return True
        if method.__returning__ is bool:
            return True
        if method.__returning__ is Message:
            chat_id = getattr(method, "chat_id", 0)
            photo = None
            if isinstance(method, SendPhoto):
                n = next(self._ids)
                photo = [PhotoSize(file_id=f"photo_{n}", file_unique_id=f"u{n}", width=768, height=1075)]
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id if isinstance(chat_id, int) else -1, type="private"),
                text=getattr(method, "text", None),
                photo=photo,
            ).as_(bot)
        raise NotImplementedError(f"FakeSession: unsupported method {type(method).__name__}")

    # --- удобные выборки ---

    def of(self, method_type: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, method_type)]

    def texts(self) -> list[str]:
        result = []
        for r in self.requests:
            text = getattr(r, "text", None) or getattr(r, "caption", None)
            if text:
                result.append(text)
        return result

    def clear(self) -> None:
        self.requests.clear()


_update_ids = itertools.count(1)
_message_ids = itertools.count(1)


_names: dict[int, str] = {}


def tg_user(user_id: int, name: str | None = None, username: str | None = None) -> User:
    """A Telegram user; the name is remembered so that later updates from them don't "rename" the player."""
    if name is not None:
        _names[user_id] = name
    return User(id=user_id, is_bot=False, first_name=_names.get(user_id, "Иван"), username=username, language_code="ru")


def message_update(
    text: str | None, user_id: int = 100, name: str | None = None, chat_type: str = "private", **extra: Any
) -> Update:
    chat_id = user_id if chat_type == "private" else -5000
    msg = Message(
        message_id=next(_message_ids),
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=tg_user(user_id, name),
        text=text,
        **extra,
    )
    return Update(update_id=next(_update_ids), message=msg)


def callback_update(data: str, user_id: int = 100) -> Update:
    msg = Message(
        message_id=next(_message_ids),
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=BOT_USER,
        text="menu",
    )
    cb = CallbackQuery(id=str(next(_update_ids)), from_user=tg_user(user_id), chat_instance="ci", message=msg, data=data)
    return Update(update_id=next(_update_ids), callback_query=cb)


def pre_checkout_update(payload: str, currency: str, amount: int, user_id: int = 100) -> Update:
    query = PreCheckoutQuery(
        id=str(next(_update_ids)),
        from_user=tg_user(user_id),
        currency=currency,
        total_amount=amount,
        invoice_payload=payload,
    )
    return Update(update_id=next(_update_ids), pre_checkout_query=query)


def payment_update(
    payload: str, currency: str, amount: int, charge_id: str, user_id: int = 100, **extra: Any
) -> Update:
    sp = SuccessfulPayment(
        currency=currency,
        total_amount=amount,
        invoice_payload=payload,
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id="",
        **extra,
    )
    return message_update(None, user_id=user_id, successful_payment=sp)


def inline_update(query: str, user_id: int = 100) -> Update:
    iq = InlineQuery(id=str(next(_update_ids)), from_user=tg_user(user_id), query=query, offset="")
    return Update(update_id=next(_update_ids), inline_query=iq)
