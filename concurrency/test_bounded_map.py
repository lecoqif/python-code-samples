"""Ordering, submission bounds, and worker ownership under failure."""

import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, current_thread

import pytest

from concurrency import bounded_map
from concurrency.bounded_map import async_map_with_limit, bounded_parallel_map


@pytest.mark.parametrize("items", [[], [0], list(range(7))])
def test_threaded_map_accepts_iterators_and_none_results(items):
    threads = set()
    lock = Lock()

    def work(value):
        with lock:
            threads.add(current_thread())
        return value * 2 if value else None

    assert bounded_parallel_map(work, iter(items)) == [
        value * 2 if value else None for value in items
    ]
    assert all(not thread.is_alive() for thread in threads)


def test_threaded_map_refills_behind_slow_first_item_and_returns_input_order():
    third_finished = Event()
    completed = []

    def work(value):
        if value == 0:
            assert third_finished.wait(timeout=5)
        completed.append(value)
        if value == 2:
            third_finished.set()
        return value * 10

    assert bounded_parallel_map(work, range(3), max_workers=2, max_in_flight=2) == [
        0,
        10,
        20,
    ]
    assert completed == [1, 2, 0]


@pytest.mark.parametrize("workers, capacity", [(4, 1), (4, 2), (2, 5)])
def test_threaded_map_bounds_submissions_and_input_consumption(
    monkeypatch, workers, capacity
):
    release = Event()
    consumed = []
    real_wait = bounded_map.wait
    first_wait = True

    class CheckedExecutor(ThreadPoolExecutor):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.submitted = []

        def submit(self, fn, /, *args, **kwargs):
            assert sum(not future.done() for future in self.submitted) < capacity
            future = super().submit(fn, *args, **kwargs)
            self.submitted.append(future)
            return future

    def checked_wait(futures, **kwargs):
        nonlocal first_wait
        assert len(futures) <= capacity
        if first_wait:
            first_wait = False
            # Workers stay blocked until the coordinator has filled its window.
            assert consumed == list(range(capacity))
            release.set()
        return real_wait(futures, **kwargs)

    def inputs():
        for value in range(12):
            consumed.append(value)
            yield value

    def work(value):
        assert release.wait(timeout=5)
        return value

    monkeypatch.setattr(bounded_map, "ThreadPoolExecutor", CheckedExecutor)
    monkeypatch.setattr(bounded_map, "wait", checked_wait)
    assert bounded_parallel_map(
        work, inputs(), max_workers=workers, max_in_flight=capacity
    ) == list(range(12))
    assert not first_wait


def test_threaded_failure_stops_consuming_and_joins_running_callback(monkeypatch):
    started = Event()
    joining = Event()
    release = Event()
    finished = Event()
    consumed = []
    threads = []
    failure = OSError("callback failed")

    class ObservedExecutor(ThreadPoolExecutor):
        def shutdown(self, wait=True, *, cancel_futures=False):
            joining.set()
            return super().shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(bounded_map, "ThreadPoolExecutor", ObservedExecutor)

    def inputs():
        for value in range(10):
            consumed.append(value)
            yield value

    def work(value):
        threads.append(current_thread())
        if value == 0:
            started.set()
            assert release.wait(timeout=5)
            finished.set()
            return value
        assert started.wait(timeout=5)
        raise failure

    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(bounded_parallel_map, work, inputs(), max_workers=2)
        try:
            assert joining.wait(timeout=5)
            assert not result.done()
        finally:
            release.set()
        with pytest.raises(OSError) as caught:
            result.result(timeout=5)
    assert caught.value is failure
    assert consumed == [0, 1]
    assert finished.is_set()
    assert all(not thread.is_alive() for thread in threads)


def test_threaded_iterator_failure_joins_submitted_work():
    started = Event()
    failing = Event()
    release = Event()
    finished = Event()
    failure = ValueError("input failed")

    def inputs():
        yield 0
        assert started.wait(timeout=5)
        failing.set()
        raise failure

    def work(value):
        started.set()
        assert release.wait(timeout=5)
        finished.set()
        return value

    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(bounded_parallel_map, work, inputs())
        try:
            assert failing.wait(timeout=5)
            assert not result.done()
        finally:
            release.set()
        with pytest.raises(ValueError) as caught:
            result.result(timeout=5)
    assert caught.value is failure
    assert finished.is_set()


@pytest.mark.parametrize("capacity", [0, -1])
def test_threaded_nonpositive_capacity_is_rejected(capacity):
    with pytest.raises(ValueError, match="max_in_flight must be positive"):
        bounded_parallel_map(str, [], max_in_flight=capacity)


def test_threaded_invalid_worker_count_uses_executor_validation():
    with pytest.raises(ValueError):
        bounded_parallel_map(str, [], max_workers=0, max_in_flight=1)


def run_async(coroutine):
    # Bound regressions without using sleeps to decide whether work finished.
    return asyncio.run(asyncio.wait_for(coroutine, timeout=5))


@pytest.mark.parametrize("items", [[], [0], list(range(7))])
def test_async_map_accepts_iterators_and_none_results(items):
    async def work(value):
        return value * 2 if value else None

    assert run_async(async_map_with_limit(work, iter(items))) == [
        value * 2 if value else None for value in items
    ]


def test_async_map_refills_behind_slow_first_item_and_returns_input_order():
    async def scenario():
        third_finished = asyncio.Event()
        completed = []

        async def work(value):
            if value == 0:
                await third_finished.wait()
            completed.append(value)
            if value == 2:
                third_finished.set()
            return value * 10

        assert await async_map_with_limit(work, range(3), limit=2) == [0, 10, 20]
        assert completed == [1, 2, 0]

    run_async(scenario())


@pytest.mark.parametrize("limit", [1, 2, 4])
def test_async_map_bounds_created_tasks_input_consumption_and_active_calls(limit):
    async def scenario():
        existing_tasks = asyncio.all_tasks()
        consumed = []
        barrier = asyncio.Barrier(limit)
        active = 0
        peak = 0

        def inputs():
            for value in range(limit * 3):
                consumed.append(value)
                yield value

        async def work(value):
            nonlocal active, peak
            assert len(asyncio.all_tasks() - existing_tasks) <= limit
            if value == 0:
                assert consumed == list(range(limit))
            active += 1
            peak = max(peak, active)
            try:
                await barrier.wait()
                return value
            finally:
                active -= 1

        assert await async_map_with_limit(work, inputs(), limit=limit) == list(
            range(limit * 3)
        )
        assert peak == limit
        assert active == 0
        assert asyncio.all_tasks() == existing_tasks

    run_async(scenario())


def test_async_failure_cancels_and_awaits_sibling_but_leaves_unrelated_task():
    async def scenario():
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release_cleanup = asyncio.Event()
        finished = []
        consumed = []
        failure = OSError("callback failed")
        unrelated = asyncio.create_task(asyncio.Event().wait())

        def inputs():
            for value in range(10):
                consumed.append(value)
                yield value

        async def work(value):
            if value == 0:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release_cleanup.wait()
                    finished.append(value)
            await started.wait()
            raise failure

        mapper = asyncio.create_task(async_map_with_limit(work, inputs(), limit=2))
        try:
            await cleaning.wait()
            assert not mapper.done()
            release_cleanup.set()
            with pytest.raises(OSError) as caught:
                await mapper
            assert caught.value is failure
            assert consumed == [0, 1]
            assert finished == [0]
            assert not unrelated.done()
        finally:
            release_cleanup.set()
            mapper.cancel()
            unrelated.cancel()
            await asyncio.gather(mapper, unrelated, return_exceptions=True)

    run_async(scenario())


def test_async_caller_cancellation_waits_for_all_worker_finalizers():
    async def scenario():
        full = asyncio.Event()
        cleaning = asyncio.Event()
        release_cleanup = asyncio.Event()
        started = []
        finalizing = []
        finished = []

        async def work(value):
            started.append(value)
            if len(started) == 2:
                full.set()
            try:
                await asyncio.Event().wait()
            finally:
                finalizing.append(value)
                if len(finalizing) == 2:
                    cleaning.set()
                await release_cleanup.wait()
                finished.append(value)

        mapper = asyncio.create_task(async_map_with_limit(work, range(10), limit=2))
        try:
            await full.wait()
            mapper.cancel()
            await cleaning.wait()
            assert not mapper.done()
            release_cleanup.set()
            with pytest.raises(asyncio.CancelledError):
                await mapper
            assert started == [0, 1]
            assert sorted(finished) == [0, 1]
        finally:
            release_cleanup.set()
            mapper.cancel()
            await asyncio.gather(mapper, return_exceptions=True)

    run_async(scenario())


def test_async_iterator_failure_cleans_up_running_sibling():
    async def scenario():
        started = asyncio.Event()
        finished = []
        failure = ValueError("input failed")

        def inputs():
            yield 0
            yield 1
            raise failure

        async def work(value):
            if value == 0:
                await started.wait()
                return value
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)  # Yield during cleanup, without a timing delay.
                finished.append(value)

        with pytest.raises(ValueError) as caught:
            await async_map_with_limit(work, inputs(), limit=2)
        assert caught.value is failure
        assert finished == [1]

    run_async(scenario())


def test_async_callback_can_return_a_future():
    async def scenario():
        def work(value):
            future = asyncio.get_running_loop().create_future()
            future.set_result(value)
            return future

        assert await async_map_with_limit(work, [None, 1]) == [None, 1]

    run_async(scenario())


def test_async_callback_can_raise_before_returning_an_awaitable():
    failure = OSError("callback failed before awaiting")

    def work(value):
        raise failure

    with pytest.raises(OSError) as caught:
        run_async(async_map_with_limit(work, [0]))
    assert caught.value is failure


def test_async_simultaneous_failures_are_all_retrieved():
    async def scenario():
        loop = asyncio.get_running_loop()
        errors = []
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda loop, context: errors.append(context))
        barrier = asyncio.Barrier(2)

        async def work(value):
            await barrier.wait()
            raise OSError(f"callback {value} failed")

        try:
            with pytest.raises(OSError):
                await async_map_with_limit(work, range(2), limit=2)
            gc.collect()
            assert errors == []
        finally:
            loop.set_exception_handler(old_handler)

    run_async(scenario())


@pytest.mark.parametrize("limit", [0, -1])
def test_async_nonpositive_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="limit must be positive"):
        run_async(async_map_with_limit(str, [], limit=limit))
