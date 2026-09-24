"""Basic filter for image requests: the bot doesn't generate 18+ content (Telegram rules and advertising)."""

from __future__ import annotations

import re

_RU_STEMS = (
    "порн", "секс", "эрот", "хентай", "голая", "голый", "голые", "голую", "голой", "обнаж", "нагишом",
    "сиськ", "титьк", "пизд", "хуй", "хуё", "хуе", "член в", "минет", "трах", "ебл", "ебу", "выеб",
    "проститу", "шлюх", "интим", "без одежды", "раздет",
)
_EN_WORDS = (
    "porn", "porno", "sex", "sexy", "nsfw", "nude", "nudes", "naked", "hentai", "erotic", "boobs", "tits",
    "nipple", "nipples", "pussy", "penis", "dick", "vagina", "topless", "bottomless", "undressed", "blowjob",
    "cum", "orgasm", "fetish", "bdsm", "genitals", "lewd",
)

_RU_RE = re.compile(r"(?<![а-яё])(" + "|".join(re.escape(s) for s in _RU_STEMS) + ")", re.IGNORECASE)
_EN_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _EN_WORDS) + r")\b", re.IGNORECASE)


def is_prompt_allowed(prompt: str) -> bool:
    return not (_RU_RE.search(prompt) or _EN_RE.search(prompt))
