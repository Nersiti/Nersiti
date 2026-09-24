"""GPU task queue: images are generated one after another; Premium goes first."""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")

PRIORITY_PREMIUM = 0
PRIORITY_FREE = 1
PRIORITY_BACKGROUND = 5


class GenerationQueue:
    def __init__(self, workers: int = 1) -> None:
        self.workers = max(workers, 1)
        self._queue: asyncio.PriorityQueue[tuple[int, int, Callable[[], Awaitable[Any]], asyncio.Future[Any]]] = (
            asyncio.PriorityQueue()
        )
        self._seq = itertools.count()
        self._tasks: list[asyncio.Task[None]] = []
        self._running = 0

    @property
    def load(self) -> int:
        """How many tasks are queued or running right now."""
        return self._queue.qsize() + self._running

    def start(self) -> None:
        if not self._tasks:
            self._tasks = [asyncio.create_task(self._worker(), name=f"gen-worker-{i}") for i in range(self.workers)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        while not self._queue.empty():
            *_, fut = self._queue.get_nowait()
            if not fut.done():
                fut.cancel()

    async def submit(self, job: Callable[[], Awaitable[T]], priority: int = PRIORITY_FREE) -> T:
        fut: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        await self._queue.put((priority, next(self._seq), job, fut))
        return await fut

    async def _worker(self) -> None:
        while True:
            _, _, job, fut = await self._queue.get()
            try:
                if fut.done():  # заказчик ушёл, пока ждал в очереди
                    continue
                self._running += 1
                try:
                    result = await job()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - ошибка отдаётся заказчику
                    if not fut.done():
                        fut.set_exception(e)
                else:
                    if not fut.done():
                        fut.set_result(result)
                finally:
                    self._running -= 1
            finally:
                self._queue.task_done()
