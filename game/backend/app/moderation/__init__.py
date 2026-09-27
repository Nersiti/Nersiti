"""Very small text filter for user-controlled names (clan titles).

Extend moderation/wordlist.txt: one lowercase fragment per line, # for comments.
"""

import re
from functools import lru_cache
from pathlib import Path

WORDLIST = Path(__file__).parent / "wordlist.txt"
_NORMALIZE = str.maketrans({"ё": "е", "0": "о", "@": "а", "$": "s", "3": "з"})


@lru_cache
def _fragments() -> tuple[str, ...]:
    lines = WORDLIST.read_text(encoding="utf-8").splitlines()
    return tuple(x.strip().lower() for x in lines if x.strip() and not x.startswith("#"))


def normalize(text: str) -> str:
    return re.sub(r"[\s\-_.*]+", "", text.lower().translate(_NORMALIZE))


def is_allowed(text: str) -> bool:
    norm = normalize(text)
    return not any(fragment in norm for fragment in _fragments())
