"""Words: normalization, validation, and the list of "hot" auction words."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

MAX_LEN = 32
MAX_WORDS = 4

_STRIP = "«»\"'“”„.,!?;:()[]{}<>…*_~`#@/\\|"
_ALLOWED = re.compile(r"^[^\W_](?:[\w' -]*[^\W_])?$")
_HAS_LETTER = re.compile(r"[^\W\d_]")
_SPACES = re.compile(r"\s+")


def clean(text: str) -> str:
    return _SPACES.sub(" ", text.strip().strip(_STRIP).strip())


def normalize(text: str) -> str | None:
    """Ownership key for a word: lowercase, ё→е, single spaces. None if it isn't a word."""
    word = clean(text).lower().replace("ё", "е")
    if not word or len(word) > MAX_LEN or "_" in word:
        return None
    if not _ALLOWED.match(word) or not _HAS_LETTER.search(word):
        return None
    if len(word.split(" ")) > MAX_WORDS:
        return None
    return word


def display_form(text: str) -> str:
    """How the word is shown on the card: as the player typed it, but tidy."""
    word = clean(text)[:MAX_LEN]
    return word[:1].upper() + word[1:]


@lru_cache
def reserved_words() -> tuple[str, ...]:
    """"Hot" words that can't be claimed — they're sold at the daily auction."""
    path = Path(__file__).with_name("reserved_words.txt")
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and (word := normalize(line)):
            words.append(word)
    return tuple(dict.fromkeys(words))


@lru_cache
def _reserved_set() -> frozenset[str]:
    return frozenset(reserved_words())


def is_reserved(word: str) -> bool:
    return word in _reserved_set()
