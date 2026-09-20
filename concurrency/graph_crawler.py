"""Concurrent graph traversal with bounded dispatch and explicit failure handling."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar

Node = TypeVar("Node", bound=Hashable)


def crawl_graph(
    start: Node,
    get_neighbors: Callable[[Node], list[Node]],
    *,
    max_workers: int = 4,
) -> set[Node]:
    """Return all nodes reachable from start, fetching each node at most once.

    Only the coordinator modifies traversal state. Worker threads call
    get_neighbors, which must be safe for concurrent use and return a list.
    Nodes must have stable hashes and equality. Traversal order is unspecified.

    At most max_workers fetches are outstanding, including queued futures.
    The frontier and discovered set can still grow with the reachable graph.

    On an observed error, stop dispatching, cancel work that has not started,
    wait for running calls, then propagate the error. Python cannot forcibly
    stop a running thread: callbacks must finish and set their own I/O timeouts.
    All worker threads are joined before this function returns or raises.
    """
    seen = {start}
    pending = deque([start])
    in_flight: set[Future[list[Node]]] = set()

    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="graph-crawler"
    ) as executor:
        try:
            while pending or in_flight:
                while pending and len(in_flight) < max_workers:
                    node = pending.popleft()
                    in_flight.add(executor.submit(get_neighbors, node))

                completed, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in completed:
                    # result() propagates callback exceptions to the caller.
                    for neighbor in future.result():
                        if neighbor not in seen:
                            # Reserve at discovery, before any worker can fetch it.
                            seen.add(neighbor)
                            pending.append(neighbor)
        finally:
            for future in in_flight:
                future.cancel()

    return seen
