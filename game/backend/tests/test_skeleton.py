from app.i18n import pick_lang, t


def start_update(text: str, user_id: int = 42, lang: str = "ru") -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Ivan", "language_code": lang},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
        },
    }


async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


async def test_webhook_rejects_wrong_secret(client, bot_session):
    res = await client.post(
        "/tg/webhook",
        json=start_update("/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert res.status_code == 403
    assert bot_session.calls == []


async def test_start_sends_webapp_button_with_start_param(client, bot_session):
    res = await client.post(
        "/tg/webhook",
        json=start_update("/start r_777"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
    )
    assert res.status_code == 200
    [sent] = bot_session.of_type("SendMessage")
    assert sent.chat_id == 42
    assert "Битва за Мир" in sent.text
    button = sent.reply_markup.inline_keyboard[0][0]
    assert button.web_app.url == "https://game.test/?sp=r_777"


async def test_start_ignores_malformed_param(client, bot_session):
    await client.post(
        "/tg/webhook",
        json=start_update("/start <script>", lang="en"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
    )
    [sent] = bot_session.of_type("SendMessage")
    assert sent.reply_markup.inline_keyboard[0][0].web_app.url == "https://game.test/"
    assert "Play" in sent.reply_markup.inline_keyboard[0][0].text


def test_pick_lang():
    assert pick_lang("ru") == "ru"
    assert pick_lang("uk") == "ru"
    assert pick_lang("pt-br") == "en"
    assert pick_lang(None) == "en"
    assert t("en", "start.button") == "🌍 Play"


def test_locales_have_the_same_keys():
    import json
    from pathlib import Path

    locales = Path(__file__).resolve().parents[1] / "app" / "locales"
    ru = json.loads((locales / "ru.json").read_text(encoding="utf-8"))
    en = json.loads((locales / "en.json").read_text(encoding="utf-8"))
    assert set(ru) == set(en)
