"""Deterministic coordination and failure checks for the concurrent crawler."""

import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from textwrap import dedent
from threading import Barrier, Event, Lock, current_thread

import pytest

from concurrency.graph_crawler import crawl_graph


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_cycles_duplicates_and_disconnected_nodes(workers):
    graph = {
        "root": ["a", "b", "a"],
        "a": ["c", "root"],
        "b": ["c", "d"],
        "c": ["e"],
        "d": ["e"],
        "e": [],
        "unreachable": ["root"],
    }
    calls = Counter()
    threads = set()
    lock = Lock()

    def neighbors(node):
        with lock:
            calls[node] += 1
            threads.add(current_thread())
        return graph[node]

    reachable = set(graph) - {"unreachable"}
    assert crawl_graph("root", neighbors, max_workers=workers) == reachable
    assert calls == Counter({node: 1 for node in reachable})
    assert all(not thread.is_alive() for thread in threads)


def test_simultaneous_discovery_fetches_shared_child_once():
    rendezvous = Barrier(2)
    calls = Counter()
    lock = Lock()

    def neighbors(node):
        with lock:
            calls[node] += 1
        if node == "root":
            return ["left", "right"]
        if node in {"left", "right"}:
            rendezvous.wait(timeout=5)
            return ["shared", "shared"]
        return []

    expected = {"root", "left", "right", "shared"}
    assert crawl_graph("root", neighbors, max_workers=2) == expected
    assert calls == Counter({node: 1 for node in expected})


def test_parallel_fetches_respect_worker_limit():
    release = Event()
    full = Event()
    lock = Lock()
    active = 0
    peak = 0

    def neighbors(node):
        nonlocal active, peak
        if node == "root":
            return list(range(12))
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 3:
                full.set()
        try:
            assert release.wait(timeout=5), "test did not release fetches"
        finally:
            with lock:
                active -= 1
        return []

    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(crawl_graph, "root", neighbors, max_workers=3)
        try:
            assert full.wait(timeout=5), "fetches did not overlap"
            assert not result.done()
        finally:
            release.set()
        assert result.result(timeout=5) == {"root", *range(12)}
    assert peak == 3
    assert active == 0


def test_outstanding_futures_are_bounded(monkeypatch):
    """Check dispatch capacity, not just the executor's active-thread limit."""
    from concurrency import graph_crawler

    class CapacityCheckedExecutor(ThreadPoolExecutor):
        def __init__(self, max_workers, **kwargs):
            super().__init__(max_workers=max_workers, **kwargs)
            self.submitted = []
            self.capacity = max_workers

        def submit(self, fn, /, *args, **kwargs):
            assert sum(not future.done() for future in self.submitted) < self.capacity
            future = super().submit(fn, *args, **kwargs)
            self.submitted.append(future)
            return future

    monkeypatch.setattr(graph_crawler, "ThreadPoolExecutor", CapacityCheckedExecutor)
    rendezvous = Barrier(3)

    def neighbors(node):
        if node == "root":
            return list(range(9))
        rendezvous.wait(timeout=5)
        return []

    assert crawl_graph("root", neighbors, max_workers=3) == {"root", *range(9)}


def test_root_failure_propagates_original_exception_and_joins_workers():
    failure = OSError("fetch failed")
    threads = []

    def neighbors(node):
        threads.append(current_thread())
        raise failure

    with pytest.raises(OSError) as caught:
        crawl_graph("root", neighbors)
    assert caught.value is failure
    assert all(not thread.is_alive() for thread in threads)


def test_failure_with_pending_nodes_does_not_hang():
    # A separate process bounds this regression test if shutdown ever deadlocks.
    program = dedent("""\
        from concurrency.graph_crawler import crawl_graph

        calls = []
        failure = OSError("fetch failed")
        def neighbors(node):
            calls.append(node)
            if node == "root":
                return ["bad", "undispatched"]
            raise failure

        try:
            crawl_graph("root", neighbors, max_workers=1)
        except OSError as error:
            assert error is failure
        else:
            raise AssertionError("callback failure was swallowed")
        assert calls == ["root", "bad"], calls
    """)
    result = subprocess.run(
        [sys.executable, "-B", "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_failure_waits_for_running_callback_before_raising():
    slow_started = Event()
    failing = Event()
    release = Event()
    slow_finished = Event()
    failure = OSError("peer failed")

    def neighbors(node):
        if node == "root":
            return ["slow", "bad"]
        if node == "slow":
            slow_started.set()
            assert release.wait(timeout=5)
            slow_finished.set()
            return []
        assert slow_started.wait(timeout=5)
        failing.set()
        raise failure

    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(crawl_graph, "root", neighbors, max_workers=2)
        try:
            assert failing.wait(timeout=5)
            assert not result.done()
        finally:
            release.set()
        with pytest.raises(OSError) as caught:
            result.result(timeout=5)
    assert caught.value is failure
    assert slow_finished.is_set()


def test_hashable_nodes_include_none_and_integers():
    graph = {None: [0, "end"], 0: ["end"], "end": []}
    assert crawl_graph(None, graph.__getitem__) == set(graph)


def test_isolated_start_is_included():
    assert crawl_graph("root", lambda node: []) == {"root"}


@pytest.mark.parametrize("workers", [0, -1])
def test_invalid_worker_count_uses_executor_validation(workers):
    with pytest.raises(ValueError):
        crawl_graph("root", lambda node: [], max_workers=workers)
