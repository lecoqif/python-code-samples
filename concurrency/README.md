# Concurrent graph crawler

[Implementation](graph_crawler.py) · [Tests](test_graph_crawler.py)

A standalone graph traversal using Python's standard library. It overlaps
neighbor lookups, fetches each discovered node at most once, and propagates
callback failures after worker cleanup.

```python
from concurrency.graph_crawler import crawl_graph

graph = {
    "root": ["a", "b", "a"],
    "a": ["shared", "root"],
    "b": ["shared"],
    "shared": [],
}
reached = crawl_graph("root", graph.__getitem__, max_workers=4)
assert reached == {"root", "a", "b", "shared"}
```

`get_neighbors(node)` runs in a worker thread and returns a list of neighboring
nodes. The callback can perform I/O or consult an in-memory graph. It must be
safe for concurrent calls; nodes must have stable hashes and equality. Results
are a set, so traversal and completion order are unspecified.

## Coordination and ownership

The caller acts as coordinator and owns the frontier, discovered set, and
outstanding futures. Workers only run the supplied callback. Reserving nodes
when discovered ensures that cycles and simultaneous discovery cannot cause
duplicate fetches. Traversal state requires no shared-state locks.

The coordinator submits at most `max_workers` futures, waits for at least one
completion, incorporates the results, and fills the available slots. This caps
both active fetches and queued executor work. The frontier and discovered set
can still grow with the reachable graph: total traversal storage is O(V), plus
the callback result lists currently retained. Each returned edge is examined
once; the completion loop also inspects up to `max_workers` futures per batch.

## Failure and shutdown

Calling `Future.result()` exposes callback exceptions to the coordinator. On
the first observed failure, it abandons undispatched nodes, cancels futures
that have not started, waits for running callbacks, and raises the original
exception. It does not return partial results as a successful crawl. If several
callbacks fail together, which error is observed first is unspecified.

All worker threads finish before the function returns or raises. Running
callbacks cannot be forcibly interrupted: a network-backed callback needs its
own request timeouts. There is no traversal deadline or caller cancellation API.
The reachable graph must be finite for a successful crawl to terminate.

## Verification

```sh
.venv/bin/python run_samples.py graph_crawler
# Or run the standalone suite directly:
.venv/bin/python -m pytest -q concurrency/test_graph_crawler.py
```

Thirteen tests cover cycles, disconnected nodes, concurrent discovery, active
and outstanding-work bounds, propagated failures, pending work after a failure,
thread cleanup, and generic hashable nodes. Events and barriers coordinate
specific interleavings without sleeps or speed thresholds. The deadlock
regression runs in a subprocess with a timeout so a broken shutdown cannot
leave the test runner blocked indefinitely.

The implementation has no third-party runtime dependencies. Tests use pytest.
