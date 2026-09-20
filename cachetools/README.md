# Live cache resizing

[Patch](resize.patch) · [Tests](test_resize.py) ·
[Upstream baseline](https://github.com/tkem/cachetools/tree/4500e3d04288738d25acbb4973eb3c3e1bf41db9)

Adds `Cache.resize(maxsize)` and a timed-cache override to cachetools 7.1.8.
The return value is a tuple of live `(key, value)` evictions in policy order.

```python
from cachetools import LRUCache

cache = LRUCache(3)
cache.update(a=1, b=2, c=3)
cache["a"]
assert cache.resize(2) == (("b", 2),)
assert cache.maxsize == 2
```

## Design

The base implementation delegates eviction to `popitem`, so existing FIFO,
LRU, LFU, random, and custom policies retain control. Capacity uses `currsize`,
which already incorporates custom `getsizeof` weights. Increasing a budget
requires no evictions.

Timed caches validate before mutation, freeze the existing timer context,
expire stale entries, then use the same resizing path. Expired entries are
excluded from live eviction results. NaN and negative budgets are rejected;
positive infinity is accepted.

## Tests and limits

Fifteen checks cover admission after resizing, policy order, weighted values,
zero/infinite capacity, TTL/TLRU expiration, invalid-request atomicity, and a
single timer read across multiple evictions.

Runtime follows the cost of the underlying eviction policy and number of
evictions. Cache access requires external synchronization for concurrent use.
If a custom `popitem` fails partway through, earlier evictions remain; adding a
transactional guarantee would require a different extension contract.
