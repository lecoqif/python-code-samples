# Bounded parallel maps

[Implementation](bounded_map.py) · [Tests](test_bounded_map.py)

Two standalone maps for I/O workloads: one for blocking callbacks in threads,
the other for awaitable callbacks on an asyncio event loop. Both consume a
finite iterable incrementally and return a list in input order, even when
callbacks finish out of order.

```python
import asyncio

from concurrency.bounded_map import async_map_with_limit, bounded_parallel_map

# A blocking callback could fetch or parse each item.
results = bounded_parallel_map(
    str.upper, iter(["alpha", "beta", "gamma"]),
    max_workers=4, max_in_flight=8,
)
assert results == ["ALPHA", "BETA", "GAMMA"]

async def normalize(value: str) -> str:
    return value.upper()

results = asyncio.run(async_map_with_limit(normalize, ["alpha", "beta"], limit=2))
assert results == ["ALPHA", "BETA"]
```

The small callbacks above illustrate the API. In use, the threaded version
fits blocking I/O clients; the async version fits clients with awaitable I/O.
Neither interface promises CPU parallelism or limits requests per second.

## Submission and ordering

`bounded_parallel_map` separates the number of worker threads (`max_workers`)
from the submission window (`max_in_flight`, defaulting to `max_workers`). The
window includes running and queued futures. If it is smaller than the worker
count, it also limits active callbacks. `async_map_with_limit` creates at most
`limit` outstanding tasks, including tasks waiting for I/O.

Each coordinator fills available slots, waits for any completion, and records
results by input index. A slow first item does not prevent refilling slots freed
by later items. The final list restores input order; callback side effects and
the order in which callbacks start are unspecified.

Bounding submissions matters as well as bounding active calls: putting a
semaphore inside every callback would still permit creating one future or task
per input. Here, outstanding-work storage is O(window size), while retained
results require O(N) storage because the API returns a complete list. The
completion loop inspects up to one window of futures or tasks per batch. This
is not an iterator that streams results as they become available.

Only the coordinator advances the input iterator. Threaded callbacks must be
safe to run concurrently. In the async version, both input iteration and the
callback run on the event-loop thread and must avoid blocking it.

## Failure and cancellation

Callback and input-iterator errors stop further submission once observed;
the map does not return a partial result. If several callbacks fail together,
which exception is propagated is unspecified.

- **Threads:** cancel queued futures that have not started, wait for running
  callbacks, and raise the original error. All worker threads are joined before
  returning or raising. A callback that has started cannot be forcibly stopped;
  blocking I/O needs its own timeouts. There is no separate caller cancellation
  API.
- **Async:** cancel and await all owned tasks, including asynchronous finalizers,
  then propagate the original error. Cancelling the map's task follows the same
  cleanup path and propagates `CancelledError`. Unrelated event-loop tasks are
  left alone. Callbacks must cooperate with cancellation; there is no built-in
  deadline. Exceptions from sibling tasks during cleanup are retrieved without
  replacing the original error.

The async wrapper accepts any awaitable returned by the callback, including a
Future, and contains errors raised before the callback returns that awaitable.
Both APIs reject nonpositive window sizes to avoid an operation that cannot
make progress. They support `None` as an ordinary callback result.

## Verification

```sh
.venv/bin/python run_samples.py bounded_map
# Or run the standalone suite directly:
.venv/bin/python -m pytest -q concurrency/test_bounded_map.py
```

Twenty-seven tests cover empty and one-shot inputs, result ordering, refilling
behind a slow item, bounded submissions and task creation, iterator failures,
thread shutdown, callback errors, simultaneous async errors, and caller
cancellation that waits for worker finalizers. Events and barriers establish
the relevant interleavings; timeouts bound stalled tests, without making speed
an assertion. The tests also verify that async cleanup leaves unrelated tasks
alone.

The implementation uses only the Python standard library. Tests use pytest.
