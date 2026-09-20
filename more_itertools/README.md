# Bounded bucket buffering

[Patch](bounded_bucket.patch) · [Tests](test_bounded_bucket.py) ·
[Upstream baseline](https://github.com/more-itertools/more-itertools/tree/2fe1b2eeb9d75f994113fe3ac76d14b6bcd6fb10)

Extends `more_itertools.bucket` 11.1.0 with keyword-only `max_cached` and a
`cached_count` property. The default remains unlimited buffering.

```python
from more_itertools import bucket

stream = bucket(["b1", "b2", "a1"], key=lambda x: x[0], max_cached=2)
child = stream["a"]
try:
    next(child)
except BufferError:
    assert next(stream["b"]) == "b1"
assert next(child) == "a1"
```

## Design

A shared counter tracks buffered payloads across key queues. A capacity check
happens before advancing the source, so backpressure never consumes an item
that cannot be retained. Consumers can drain cached values, then retry.

A small iterator wrapper preserves the same child's usability after a
`BufferError` or a transient exception from a resumable source iterator. Normal
exhaustion permanently finishes that child. Membership checks put probed items
back, and aliases consume one shared FIFO queue per key.

## Tests and limits

Eleven checks cover source-read counts at capacity, same-child recovery,
transient source errors, aliased consumption, membership, enumeration, invalid
capacity before source access, and the unlimited default.

The bound applies to buffered payloads. Distinct key metadata and the source's
own storage can still grow. Searching for a key can scan many source items;
callbacks that fail after a source read do not roll that read back. A useful
next extension would make metadata retention an explicit configurable policy.
