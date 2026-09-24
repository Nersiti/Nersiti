"""Converting the model's Markdown into Telegram HTML and splitting long answers."""

from __future__ import annotations

import re

from app.utils import esc

_FENCE = re.compile(r"```([\w+#.-]*)[^\S\n]*\n?(.*?)```", re.S)
_FENCE_MARK = re.compile(r"```([\w+#.-]*)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text: str) -> str:
    """Hide reasoning of models like Qwen3 / DeepSeek-R1 (<think>...</think>)."""
    text = _THINK_BLOCK.sub("", text)
    start = text.find("<think>")
    if start != -1:
        text = text[:start]
    return text.lstrip()


def _tables_to_code(text: str) -> str:
    """Telegram can't render tables — show them as monospace blocks."""
    lines = text.split("\n")
    out: list[str] = []
    table: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        is_row = not in_fence and line.strip().startswith("|") and line.strip().endswith("|")
        if is_row:
            table.append(line)
            continue
        if table:
            out.extend(["```", *table, "```"] if len(table) >= 2 else table)
            table = []
        out.append(line)
    if table:
        out.extend(["```", *table, "```"] if len(table) >= 2 else table)
    return "\n".join(out)


def md_to_html(text: str) -> str:
    placeholders: list[str] = []

    def keep(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    def fence(match: re.Match[str]) -> str:
        lang, code = match.group(1), match.group(2).rstrip("\n")
        attr = f' class="language-{lang}"' if lang else ""
        return keep(f"<pre><code{attr}>{esc(code)}</code></pre>")

    text = _tables_to_code(text)
    text = _FENCE.sub(fence, text)
    if "```" in text:  # незакрытый блок кода — всё до конца считаем кодом
        head, _, tail = text.partition("```")
        lang_match = re.match(r"([\w+#.-]*)[^\S\n]*\n", tail)
        if lang_match:
            tail = tail[lang_match.end():]
        text = head + keep(f"<pre>{esc(tail.rstrip())}</pre>")
    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{esc(m.group(1))}</code>"), text)

    text = esc(text)
    text = re.sub(r"^(\s*)[*+-]\s+", r"\1• ", text, flags=re.M)
    text = re.sub(r"\*\*([^\n]+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"~~([^\n]+?)~~", r"<s>\1</s>", text)
    text = re.sub(
        r"^#{1,6}\s+(.+?)\s*#*$",
        lambda m: f"<b>{re.sub(r'</?b>', '', m.group(1))}</b>",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>',
        text,
    )
    text = _blockquotes(text)
    return _PLACEHOLDER.sub(lambda m: placeholders[int(m.group(1))], text)


def _blockquotes(text: str) -> str:
    out: list[str] = []
    quote: list[str] = []
    for line in text.split("\n"):
        if line.startswith("&gt; ") or line == "&gt;":
            quote.append(line[5:])
            continue
        if quote:
            out.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
            quote = []
        out.append(line)
    if quote:
        out.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
    return "\n".join(out)


def split_text(text: str, limit: int = 3800) -> list[str]:
    """Split Markdown into chunks without breaking code blocks."""
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunk, text = text[:cut], text[cut:].lstrip("\n")
        marks = list(_FENCE_MARK.finditer(chunk))
        if len(marks) % 2 == 1:
            lang = marks[-1].group(1)
            chunk += "\n```"
            text = f"```{lang}\n{text}"
        parts.append(chunk)
    parts.append(text)
    return [p for p in parts if p.strip()]
