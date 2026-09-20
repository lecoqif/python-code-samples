import pytest

from cachetools import (
    Cache,
    FIFOCache,
    LFUCache,
    LRUCache,
    RRCache,
    TLRUCache,
    TTLCache,
)


def test_live_resize_obeys_lru_and_updates_future_admission():
    cache = LRUCache(3)
    cache.update(a=1, b=2, c=3)
    assert cache["a"] == 1
    assert cache.resize(2) == (("b", 2),)
    assert cache.maxsize == 2
    cache["d"] = 4
    assert set(cache) == {"a", "d"}


def test_weighted_sizes_are_not_number_of_entries():
    cache = LRUCache(10, getsizeof=len)
    cache.update(a=b"123", b=b"45", c=b"")
    assert cache.resize(3) == (("a", b"123"),)
    assert cache.currsize == 2
    assert set(cache) == {"b", "c"}
    with pytest.raises(ValueError):
        cache["big"] = b"1234"


def test_expired_items_are_not_reported_as_live_evictions():
    now = [0]
    cache = TTLCache(4, ttl=5, timer=lambda: now[0])
    cache["old"] = 1
    now[0] = 4
    cache["live"] = 2
    now[0] = 5
    assert cache.resize(1) == ()
    assert list(cache) == ["live"]


def test_invalid_inputs_for_maxsize_param():
    cache = LRUCache(3)
    with pytest.raises(TypeError):
        cache.resize(True)
    with pytest.raises(TypeError):
        cache.resize("5")
    with pytest.raises(ValueError):
        cache.resize(-5)


@pytest.mark.parametrize("cache_type", [Cache, FIFOCache, LFUCache, LRUCache, RRCache])
def test_resize_zero_then_grow(cache_type):
    cache = cache_type(3)
    cache.update(a=1, b=2, c=3)
    assert dict(cache.resize(0)) == {"a": 1, "b": 2, "c": 3}
    assert cache.currsize == 0
    with pytest.raises(ValueError):
        cache["d"] = 4
    assert cache.resize(float("inf")) == ()
    cache["d"] = 4
    assert cache["d"] == 4


@pytest.mark.parametrize("cache_type", [TTLCache, TLRUCache])
@pytest.mark.parametrize("value", [float("nan"), -1])
def test_invalid_budget_does_not_expire_or_change_entries(cache_type, value):
    now = [0]
    expired = []

    class Observed(cache_type):
        def expire(self, time=None):
            result = super().expire(time)
            expired.extend(result)
            return result

    kwargs = {"ttl": 1} if cache_type is TTLCache else {"ttu": lambda k, v, t: t + 1}
    cache = Observed(3, timer=lambda: now[0], **kwargs)
    cache["a"] = 1
    now[0] = 2
    with pytest.raises(ValueError):
        cache.resize(value)
    assert expired == []
    assert cache.maxsize == 3
    assert cache.expire() == [("a", 1)]


def test_timer_is_read_once_across_multiple_evictions():
    clock_calls = []

    def timer():
        clock_calls.append(1)
        return 0

    cache = TTLCache(4, ttl=10, timer=timer)
    cache.update(a=1, b=2, c=3)
    clock_calls.clear()
    assert cache.resize(1) == (("a", 1), ("b", 2))
    assert len(clock_calls) == 1


def test_lfu_and_fifo_preserve_their_own_eviction_policies():
    fifo = FIFOCache(3)
    lfu = LFUCache(3)
    for cache in (fifo, lfu):
        cache.update(a=1, b=2, c=3)
        for key in ["a", "a", "b"]:
            assert cache[key] > 0
    assert fifo.resize(2) == (("a", 1),)
    assert lfu.resize(2) == (("c", 3),)
