import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED = ("ru", "en")
# Telegram language codes that get the Russian interface.
RU_LANGS = {"ru", "uk", "be", "kk", "uz", "ky", "tg", "hy", "az", "ka", "tk", "mo"}


def pick_lang(language_code: str | None) -> str:
    if not language_code:
        return "en"
    code = language_code.split("-")[0].lower()
    if code in SUPPORTED:
        return code
    return "ru" if code in RU_LANGS else "en"


@lru_cache
def _load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def t(lang: str, key: str, **kwargs: object) -> str:
    text = _load(lang).get(key) or _load("en").get(key) or key
    return text.format(**kwargs) if kwargs else text
