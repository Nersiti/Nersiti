"""Cleaning up model responses."""

from __future__ import annotations

import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text: str) -> str:
    """Hide reasoning of models like Qwen3 / DeepSeek-R1 (<think>...</think>)."""
    text = _THINK_BLOCK.sub("", text)
    start = text.find("<think>")
    if start != -1:
        text = text[:start]
    return text.lstrip()
