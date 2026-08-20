"""Инструменты модели для доступа в интернет (tool / function calling).

Локальная модель сама решает, когда позвать инструмент; результат
возвращается ей в контекст. Управляется секцией web в config.yaml.

Контракт (async):
    async web_search(query, max_results=5) -> list[dict]
        # [{title, url, snippet}]; провайдер из web.search_provider:
        # duckduckgo (ddgs, без ключа) | searxng (локальный) | tavily (ключ)
    async web_fetch(url, timeout=15) -> str
        # httpx GET -> trafilatura.extract -> основной текст страницы

    TOOLS_SPEC: list[dict]   # описания инструментов в формате Ollama /api/chat "tools"
    async run_tool_call(name, arguments) -> str   # диспетчер: имя -> функция

Безопасность: если web.enabled=false — инструменты отключены (модель работает
офлайн). Ограничение по таймауту и числу результатов из config.
TODO(исполнитель): по docs/PLAN.md §7 и §7a.
"""
# TODO
