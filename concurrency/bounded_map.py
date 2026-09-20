"""Ordered maps with bounded outstanding work and cleanup on failure."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from itertools import islice
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def bounded_parallel_map(
    fn: Callable[[T], R],
    items: Iterable[T],
    *,
    max_workers: int = 4,
    max_in_flight: int | None = None,
) -> list[R]:
    """Map a finite iterable in threads, returning results in input order.

    At most max_in_flight futures are outstanding (default: max_workers),
    including queued calls. Only the coordinator consumes items. Results use
    O(N) storage; the submission window uses O(max_in_flight) storage.

    On a callback or input-iterator failure, cancel work that has not started,
    join running callbacks, and raise the original exception. Running threads
    cannot be forcibly cancelled; callbacks must handle their own I/O timeouts.
    """
    if max_in_flight is None:
        max_in_flight = max_workers
    if max_in_flight < 1:
        raise ValueError("max_in_flight must be positive")

    source = enumerate(items)
    results: dict[int, R] = {}
    pending: dict[Future[R], int] = {}
    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="bounded-map"
    ) as executor:
        try:
            while True:
                for index, item in islice(source, max_in_flight - len(pending)):
                    pending[executor.submit(fn, item)] = index
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    result = future.result()
                    results[pending.pop(future)] = result
        finally:
            for future in pending:
                future.cancel()
    return [results[index] for index in range(len(results))]


async def async_map_with_limit(
    fn: Callable[[T], Awaitable[R]],
    items: Iterable[T],
    *,
    limit: int = 4,
) -> list[R]:
    """Map a finite iterable with at most limit tasks, preserving input order.

    Consume items incrementally on the event-loop thread; the iterable and
    callback must not perform blocking I/O there. Results use O(N) storage;
    outstanding tasks use O(limit) storage.

    On callback failure, input-iterator failure, or caller cancellation,
    cancel and await all owned tasks before propagating the original error.
    Callbacks must cooperate with cancellation for cleanup to finish.
    """
    if limit < 1:
        raise ValueError("limit must be positive")

    async def invoke(item: T) -> R:
        # Own a task even when fn returns a Future or raises before awaiting.
        return await fn(item)

    source = enumerate(items)
    results: dict[int, R] = {}
    pending: dict[asyncio.Task[R], int] = {}
    try:
        while True:
            for index, item in islice(source, limit - len(pending)):
                pending[asyncio.create_task(invoke(item))] = index
            if not pending:
                break
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result = task.result()
                results[pending.pop(task)] = result
    finally:
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return [results[index] for index in range(len(results))]
