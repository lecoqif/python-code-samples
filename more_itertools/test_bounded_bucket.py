import pytest

from more_itertools import bucket


def test_same_child_recovers_after_other_consumer_drains():
    stream = bucket(["b1", "b2", "a1"], key=lambda value: value[0], max_cached=2)
    child = stream["a"]
    with pytest.raises(BufferError):
        next(child)
    assert stream.cached_count == 2
    assert next(stream["b"]) == "b1"
    assert next(child) == "a1"
    assert stream.cached_count == 1


def test_membership_retains_payload_and_invalid_keys_do_not_pull():
    reads = []

    def source():
        for value in ["a1", "b1"]:
            reads.append(value)
            yield value

    stream = bucket(
        source(),
        key=lambda value: value[0],
        validator=lambda key: key in {"a", "b"},
        max_cached=1,
    )
    assert "x" not in stream
    assert reads == []
    assert "a" in stream
    assert stream.cached_count == 1
    assert next(stream["a"]) == "a1"
    assert stream.cached_count == 0


def test_default_remains_unlimited():
    stream = bucket(range(20), key=lambda value: value % 2)
    assert list(stream[1]) == list(range(1, 20, 2))
    assert list(stream[0]) == list(range(0, 20, 2))


def test_max_cached_invalid_value():
    with pytest.raises(ValueError):
        _ = bucket(["b1", "b2", "a1"], key=lambda value: value[0], max_cached=-2)

    with pytest.raises(ValueError):
        _ = bucket(["b1", "b2", "a1"], key=lambda value: value[0], max_cached=True)

    with pytest.raises(ValueError):
        _ = bucket(["b1", "b2", "a1"], key=lambda value: value[0], max_cached=2.0)


def test_same_child_recovers_after_other_consumer_drains_interleaved():
    stream = bucket(["a1", "b1", "a2", "b2"], key=lambda value: value[0], max_cached=2)
    assert stream.cached_count == 0
    assert next(stream["a"]) == "a1"
    assert next(stream["b"]) == "b1"
    assert next(stream["a"]) == "a2"
    assert next(stream["b"]) == "b2"
    assert stream.cached_count == 0


def test_iterator_with_interleaved_values_and_next_calls():
    stream = bucket(["a1", "b1", "a2", "b2"], key=lambda value: value[0], max_cached=2)

    with pytest.raises(BufferError):
        list(stream)

    assert next(stream["a"]) == "a1"
    assert next(stream["b"]) == "b1"

    with pytest.raises(BufferError):
        list(stream)

    assert next(stream["a"]) == "a2"
    assert next(stream["b"]) == "b2"

    vals = list(stream)
    assert vals == ["a", "b"]


def test_ordering_of_contains_call():
    stream = bucket(["a1", "a2", "b1", "b2"], key=lambda value: value[0], max_cached=2)
    assert "a" in stream
    assert next(stream["a"]) == "a1"


def test_full_buffer_does_not_read_ahead_and_same_child_resumes():
    reads = []

    def source():
        for item in ["b1", "b2", "a1"]:
            reads.append(item)
            yield item

    stream = bucket(source(), key=lambda item: item[0], max_cached=2)
    child = stream["a"]
    for _ in range(2):
        with pytest.raises(BufferError):
            next(child)
        assert reads == ["b1", "b2"]
        assert stream.cached_count == 2
    assert next(stream["b"]) == "b1"
    assert next(child) == "a1"
    assert reads == ["b1", "b2", "a1"]
    assert list(stream["b"]) == ["b2"]


def test_same_child_survives_transient_source_error():
    class Source:
        def __init__(self):
            self.calls = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.calls += 1
            if self.calls == 1:
                raise OSError("retryable source failure")
            if self.calls == 2:
                return "a1"
            raise StopIteration

    stream = bucket(Source(), key=lambda item: item[0], max_cached=1)
    child = stream["a"]
    with pytest.raises(OSError):
        next(child)
    assert next(child) == "a1"
    with pytest.raises(StopIteration):
        next(child)
    with pytest.raises(StopIteration):
        next(child)


def test_aliases_share_fifo_and_accounting():
    stream = bucket(["b1", "a1", "b2", "a2"], key=lambda x: x[0], max_cached=4)
    assert list(stream["a"]) == ["a1", "a2"]
    first, second = stream["b"], stream["b"]
    assert next(first) == "b1"
    assert next(second) == "b2"
    assert stream.cached_count == 0


def test_invalid_capacity_is_rejected_before_opening_source():
    class Source:
        def __iter__(self):
            pytest.fail("invalid input opened the source")

    with pytest.raises(ValueError):
        bucket(Source(), key=str, max_cached=0)
