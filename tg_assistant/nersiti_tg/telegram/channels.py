"""Управление каналами по промту: список, предложение «что почистить», выход.

Удаление (выход) из канала — ДЕЙСТВИЕ НЕОБРАТИМОЕ, поэтому разделено на два шага:
  1) propose_cleanup(...) — ИИ по твоему промту предлагает список каналов на выход
     с причинами. НИЧЕГО не удаляет.
  2) leave_channels(...) — выполняет выход только после явного подтверждения (UI).

client — объект с async-методами (Telethon TelegramClient или совместимый):
  - async iter_dialogs()  -> объекты с .id, .name/.title, .is_channel, .unread_count
  - async delete_dialog(entity)  -> выход из канала/чата
Логика разбора решения ИИ вынесена в чистую функцию parse_cleanup_decision —
она тестируется без Telegram и без модели.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


def parse_cleanup_decision(llm_output: str, channels: list[dict]) -> list[int]:
    """Из ответа ИИ достать id каналов на выход.

    Ожидаем JSON вида {"leave":[id,...]} ИЛИ просто перечисление id в тексте.
    Возвращаем только id, реально присутствующие в channels.
    """
    valid = {int(c["id"]) for c in channels}
    ids: list[int] = []
    # 1) попытка распарсить JSON-блок
    m = re.search(r"\{.*\}", llm_output, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            for x in data.get("leave", []):
                if int(x) in valid:
                    ids.append(int(x))
            if ids:
                return list(dict.fromkeys(ids))
        except Exception:
            pass
    # 2) fallback: любые числа из текста, совпавшие с id каналов
    for n in re.findall(r"-?\d+", llm_output):
        if int(n) in valid:
            ids.append(int(n))
    return list(dict.fromkeys(ids))


class ChannelManager:
    def __init__(self, client):
        self.client = client

    async def list_channels(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for d in self.client.iter_dialogs():
            if getattr(d, "is_channel", False):
                out.append({
                    "id": int(getattr(d, "id", 0)),
                    "title": getattr(d, "name", "") or getattr(d, "title", ""),
                    "unread": int(getattr(d, "unread_count", 0) or 0),
                })
        return out

    async def propose_cleanup(self, prompt: str, ollama,
                              channels: Optional[list[dict]] = None) -> dict[str, Any]:
        """Вернуть предложение: {"leave":[{id,title,reason}], "raw": ...}. Не удаляет."""
        if channels is None:
            channels = await self.list_channels()
        listing = "\n".join(f'{c["id"]}: {c["title"]} (непрочитано {c["unread"]})'
                            for c in channels)
        sys = ("Ты помогаешь чистить список Telegram-каналов. Пользователь дал "
               "критерий. Верни СТРОГО JSON: {\"leave\":[id,...]} — id каналов, "
               "которые подходят под критерий на выход. Только JSON.")
        user = f"Критерий: {prompt}\n\nКаналы:\n{listing}"
        raw = await ollama.generate(user, system=sys)
        ids = parse_cleanup_decision(raw, channels)
        by_id = {c["id"]: c for c in channels}
        leave = [{"id": i, "title": by_id[i]["title"]} for i in ids]
        return {"leave": leave, "raw": raw}

    async def leave_channels(self, channel_ids: list[int]) -> dict[str, Any]:
        """Выполнить выход. Вызывать ТОЛЬКО после подтверждения пользователя."""
        done, failed = [], []
        for cid in channel_ids:
            try:
                await self.client.delete_dialog(cid)
                done.append(cid)
            except Exception as e:  # noqa
                failed.append({"id": cid, "error": str(e)})
        return {"left": done, "failed": failed}
