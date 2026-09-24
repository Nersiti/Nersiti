from __future__ import annotations

import io
import json
import random
from collections import Counter

import httpx
import pytest
from PIL import Image

from app.game import rules
from app.game.battle import Fighter, fallback_story, simulate
from app.game.genesis import NotAllowed, fallback_draft, parse_draft
from app.game.render import CardView, render_card
from app.game.words import display_form, is_reserved, normalize, reserved_words
from app.products import CATALOG, parse_payload
from app.services.formatting import strip_think
from app.services.images.base import ImageRequest
from app.services.images.comfyui import ComfyUIBackend, substitute
from app.services.images.others import gradient_png
from app.services.llm import OpenAICompatLLM
from app.services.moderation import is_prompt_allowed
from app.utils import plural
from tests.conftest import make_settings

# ---------- слова ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ёжик!  ", "ежик"),
        ("«Wi-Fi   в метро»", "wi-fi в метро"),
        ("кот учёного", "кот ученого"),
        ("C++", None),
        ("123", None),
        ("!!!", None),
        ("раз два три четыре пять", None),
        ("a" * 40, None),
        ("snake_case", None),
        ("rock'n'roll", "rock'n'roll"),
    ],
)
def test_normalize(raw: str, expected: str | None) -> None:
    assert normalize(raw) == expected


def test_display_form_and_reserved() -> None:
    assert display_form("  «бывший»! ") == "Бывший"
    words = reserved_words()
    assert len(words) >= 100 and all(normalize(w) == w for w in words)
    assert is_reserved("деньги") and is_reserved("черная дыра") and not is_reserved("бывший")


# ---------- правила ----------


def test_levels_and_value() -> None:
    assert [rules.level_for_xp(x) for x in (0, 99, 100, 299, 300, 10**9)] == [1, 1, 2, 2, 3, rules.MAX_LEVEL]
    assert rules.card_value("legendary", 1) == 300 and rules.card_value("common", 11) == 40


def test_make_stats_scales_with_rarity() -> None:
    rng = random.Random(1)
    common = rules.make_stats(5, 5, 5, "common", rng)
    mythic = rules.make_stats(5, 5, 5, "mythic", rng)
    assert all(m > c for m, c in zip(mythic, common, strict=True))
    assert rules.make_stats(100, -5, 0, "rare", rng)[0] > 0


def test_rarity_distribution() -> None:
    rng = random.Random(42)
    free = Counter(rules.roll_rarity(rng) for _ in range(20000))
    lord = Counter(rules.roll_rarity(rng, lord=True) for _ in range(20000))
    assert free["common"] > free["rare"] > free["epic"] > free["legendary"] > free["mythic"] > 0
    assert lord["legendary"] > free["legendary"] * 1.4
    assert set(Counter(rules.roll_rarity(rng, allowed=["legendary", "mythic"]) for _ in range(100))) <= {
        "legendary",
        "mythic",
    }


def test_elements_and_elo() -> None:
    assert rules.element_multiplier("fire", "nature") == rules.ADVANTAGE
    assert rules.element_multiplier("nature", "fire") == 1.0
    assert rules.element_multiplier("dark", "light") == rules.element_multiplier("light", "dark") == rules.ADVANTAGE
    assert rules.elo(1000, 1000) == 12 and rules.elo(1400, 1000) < rules.elo(1000, 1400)


# ---------- бой ----------


def _fighter(**kw: object) -> Fighter:
    base = {"name": "A", "word": "a", "element": "fire", "klass": "warrior", "atk": 40, "def_": 30, "hp": 100}
    base.update(kw)
    return Fighter(**base)  # type: ignore[arg-type]


def test_simulation_is_reproducible_and_favours_stronger() -> None:
    strong = _fighter(atk=90, def_=60, hp=220)
    weak = _fighter(name="B", atk=30, def_=20, hp=80)
    r1 = simulate(strong, weak, random.Random(7))
    r2 = simulate(strong, weak, random.Random(7))
    assert r1 == r2 and r1.attacker_won
    wins = sum(simulate(_fighter(), _fighter(name="B"), random.Random(i)).attacker_won for i in range(400))
    assert 120 < wins < 280  # равные бойцы — примерно поровну
    story = fallback_story(strong, weak, r1)
    assert "A" in story and "B" in story and story == fallback_story(strong, weak, r1)


def test_class_perks_applied() -> None:
    assert _fighter(klass="warrior").atk == 48
    assert _fighter(klass="guardian").def_ == 39
    assert _fighter(klass="titan").hp == 120
    assert _fighter(klass="spirit", level=3).atk == 44


# ---------- генерация существ ----------


def test_parse_draft() -> None:
    raw = 'Конечно! {"allowed": true, "name": "Кофеин", "element": "fire", "class": "mage", "atk": 12, "def": "3"}'
    draft = parse_draft(raw, "кофе")
    assert (draft.name, draft.element, draft.klass, draft.atk, draft.def_) == ("Кофеин", "fire", "mage", 10.0, 3.0)
    assert draft.ability  # недостающие поля заполняются
    with pytest.raises(NotAllowed):
        parse_draft('{"allowed": false, "reason": "политика"}', "x")
    with pytest.raises(ValueError):
        parse_draft("без json", "x")
    weird = parse_draft('{"element": "plasma", "class": "bard"}', "x")
    assert weird.element in rules.ELEMENTS and weird.klass in rules.CLASSES


def test_fallback_is_deterministic() -> None:
    assert fallback_draft("лужа") == fallback_draft("лужа")


# ---------- отрисовка ----------


def test_drawable_strips_emoji() -> None:
    from app.game.render import _drawable

    assert _drawable("Аня 🌸✨ ❤️ ⭐") == "Аня"
    assert _drawable("Wi-Fi в метро — «№1»") == "Wi-Fi в метро — «№1»"
    assert _drawable("👨‍👩‍👧") == ""


async def test_unsafe_llm_text_falls_back() -> None:
    from app.game.genesis import invent_creature

    class Rude:
        async def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return '{"allowed": true, "name": "Порно-гоблин", "element": "fire", "class": "mage"}'

    draft = await invent_creature(Rude(), "гоблин")  # type: ignore[arg-type]
    assert draft == fallback_draft("гоблин")


def test_render_card() -> None:
    view = CardView(
        word="Wi-Fi в метро", name="Сигналий", title="Неуловимый", element="lightning", klass="rogue",
        rarity="mythic", atk=74, def_=40, hp=180, ability="Одна палка",
        ability_text="Появляется на секунду, чтобы исчезнуть навсегда. " * 5,
        number=7, creator="Аня 🌸", bot_username="word_bot",
    )
    for art in (gradient_png(64, 64, 3), None, b"not an image"):
        image = Image.open(io.BytesIO(render_card(view, art)))
        assert image.format == "JPEG" and image.size == (768, 1075)


# ---------- инфраструктура ----------


def test_catalog_is_valid() -> None:
    for p in CATALOG:
        assert len(p.title) <= 32 and len(p.description) <= 255
        assert p.stars >= 1 and p.rub >= 99 and (p.crystals or p.premium_days)
        assert parse_payload(f"{p.code}:123") == (p.code, 123)
    assert parse_payload("garbage") is None


def test_strip_think_moderation_plural() -> None:
    assert strip_think("<think>хм</think>Ответ") == "Ответ" and strip_think("Ответ<think>ещё") == "Ответ"
    assert is_prompt_allowed("кот учёного") and not is_prompt_allowed("голая") and not is_prompt_allowed("nsfw")
    assert [plural(n, "слово", "слова", "слов") for n in (1, 3, 5, 11, 21)] == ["слово", "слова", "слов", "слов", "слово"]


def test_comfy_substitution_keeps_types() -> None:
    template = {"a": {"inputs": {"seed": "{{seed}}", "text": "{{prompt}}, extra", "w": "{{width}}", "x": "{{unknown}}"}}}
    result = substitute(template, {"seed": 7, "prompt": "cat", "width": 1024})
    assert result == {"a": {"inputs": {"seed": 7, "text": "cat, extra", "w": 1024, "x": "{{unknown}}"}}}


async def test_comfyui_backend_flow() -> None:
    png = gradient_png(8, 8, 1)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/prompt":
            workflow = json.loads(request.content)["prompt"]
            assert workflow["3"]["inputs"]["seed"] == 123 and workflow["4"]["inputs"]["ckpt_name"] == "model.safetensors"
            return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            if calls.count("/history/p1") < 2:
                return httpx.Response(200, json={})
            outputs = {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "temp"}]}}
            return httpx.Response(200, json={"p1": {"status": {"status_str": "success", "completed": True}, "outputs": outputs}})
        if request.url.path == "/view":
            return httpx.Response(200, content=png)
        return httpx.Response(404)

    backend = ComfyUIBackend("http://comfy", "workflows/sdxl.json", "model.safetensors", timeout=10, poll_interval=0.01)
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await backend.generate(ImageRequest("cat", "", 1024, 1024, 123, 20, 6.0)) == png
    await backend.close()


async def test_openai_compatible_llm(tmp_path) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:7b" and request.headers["Authorization"] == "Bearer ollama"
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>x</think>Готово"}}]})

    llm = OpenAICompatLLM(make_settings(tmp_path, llm_backend="openai"))
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=llm._client.headers)
    assert await llm.complete([{"role": "user", "content": "hi"}]) == "Готово"
    await llm.close()
