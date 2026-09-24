from __future__ import annotations

import json

import httpx

from app.products import CATALOG, parse_payload
from app.services.formatting import md_to_html, split_text, strip_think
from app.services.images import build_request
from app.services.images.comfyui import ComfyUIBackend, substitute
from app.services.images.others import gradient_png
from app.services.llm import OpenAICompatLLM
from app.services.moderation import is_prompt_allowed
from app.utils import plural
from tests.conftest import make_settings


def test_markdown_to_html() -> None:
    html = md_to_html("# Заголовок\n**жирный** и *курсив*, `a<b`\n- пункт\n```python\nif a < b:\n    pass\n```")
    assert "<b>Заголовок</b>" in html
    assert "<b>жирный</b>" in html and "<i>курсив</i>" in html
    assert "<code>a&lt;b</code>" in html
    assert "• пункт" in html
    assert '<pre><code class="language-python">if a &lt; b:\n    pass</code></pre>' in html


def test_markdown_links_tables_and_snake_case() -> None:
    html = md_to_html("[сайт](https://example.com/?a=1&b=2) my_var_name 2*3*4\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<a href="https://example.com/?a=1&amp;b=2">сайт</a>' in html
    assert "my_var_name" in html and "<i>" not in html
    assert "<pre><code>| a | b |" in html


def test_unclosed_code_block() -> None:
    html = md_to_html("Код:\n```js\nconsole.log(1 < 2)")
    assert html.endswith("<pre>console.log(1 &lt; 2)</pre>")


def test_split_keeps_code_blocks_balanced() -> None:
    text = "Начало\n\n```python\n" + "print('x')\n" * 800 + "```\nКонец"
    parts = split_text(text, limit=3000)
    assert len(parts) > 1
    assert all(p.count("```") % 2 == 0 for p in parts)
    assert all(len(p) <= 3010 for p in parts)


def test_strip_think() -> None:
    assert strip_think("<think>размышляю</think>Ответ") == "Ответ"
    assert strip_think("Ответ<think>ещё думаю") == "Ответ"


def test_moderation() -> None:
    assert is_prompt_allowed("кот-космонавт на Луне")
    assert is_prompt_allowed("Moby the whale in the Sussex sea")
    assert not is_prompt_allowed("голая девушка")
    assert not is_prompt_allowed("nude woman on the beach")
    assert not is_prompt_allowed("NSFW art")


def test_plural() -> None:
    assert [plural(n, "кредит", "кредита", "кредитов") for n in (1, 2, 5, 11, 21, 104)] == [
        "кредит", "кредита", "кредитов", "кредитов", "кредит", "кредита",
    ]


def test_catalog_is_valid() -> None:
    for p in CATALOG:
        assert len(p.title) <= 32 and len(p.description) <= 255
        assert p.stars >= 1 and p.rub >= 99
        assert parse_payload(f"{p.code}:123") == (p.code, 123)
    assert parse_payload("garbage") is None


def test_comfy_substitution_keeps_types() -> None:
    template = {"a": {"inputs": {"seed": "{{seed}}", "text": "{{prompt}}, extra", "w": "{{width}}", "x": "{{unknown}}"}}}
    result = substitute(template, {"seed": 7, "prompt": "cat", "width": 1024})
    assert result == {"a": {"inputs": {"seed": 7, "text": "cat, extra", "w": 1024, "x": "{{unknown}}"}}}


def test_build_request_scales_size(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, image_size_scale=0.5)
    req = build_request(settings, "cat", "photo", "9x16", seed=5)
    assert (req.width, req.height, req.seed) == (384, 672, 5)
    assert "photorealistic" in req.prompt and "cartoon" in req.negative


async def test_comfyui_backend_flow() -> None:
    png = gradient_png(8, 8, 1)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/prompt":
            workflow = json.loads(request.content)["prompt"]
            assert workflow["3"]["inputs"]["seed"] == 123
            assert workflow["4"]["inputs"]["ckpt_name"] == "model.safetensors"
            return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            if calls.count("/history/p1") < 2:
                return httpx.Response(200, json={})
            outputs = {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "temp"}]}}
            return httpx.Response(200, json={"p1": {"status": {"status_str": "success", "completed": True}, "outputs": outputs}})
        if request.url.path == "/view":
            assert request.url.params["type"] == "temp"
            return httpx.Response(200, content=png)
        return httpx.Response(404)

    backend = ComfyUIBackend("http://comfy", "workflows/sdxl.json", "model.safetensors", timeout=10, poll_interval=0.01)
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from app.services.images.base import ImageRequest

    data = await backend.generate(ImageRequest("cat", "", 1024, 1024, 123, 20, 6.0))
    assert data == png
    await backend.close()


async def test_openai_compatible_streaming(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sse = (
        'data: {"choices":[{"delta":{"content":"При"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"вет"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:7b" and request.headers["Authorization"] == "Bearer ollama"
        if body["stream"]:
            return httpx.Response(200, text=sse, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>x</think>Готово"}}]})

    llm = OpenAICompatLLM(make_settings(tmp_path, llm_backend="openai"))
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=llm._client.headers)
    chunks = [c async for c in llm.stream([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "Привет"
    assert await llm.complete([{"role": "user", "content": "hi"}]) == "Готово"
    await llm.close()
