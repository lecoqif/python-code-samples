from collections import Counter
from dataclasses import replace
from random import Random

import pytest

from replicated_reader import (
    ChunkReader,
    Piece,
    ReadFailure,
    ReadPlan,
    ReadPolicy,
    Reply,
    Status,
)


def quorum(data=b"ABCDE", generation=5, start_id=0):
    return [
        Reply(Status.OK, True, start_id + i, i % 2, generation, data) for i in range(3)
    ]


class Store:
    def __init__(self, replies, pieces=(Piece(0, 1, 3, 0),), generation=5):
        self.replies = replies
        self.read_plan = ReadPlan(generation, pieces)
        self.calls = []
        self.plans = []

    def plan(self, offset, num_bytes):
        self.plans.append((offset, num_bytes))
        return self.read_plan

    def read_replicas(self, chunk):
        self.calls.append(chunk)
        return self.replies[chunk]


def test_primary_uses_lowest_eligible_replica_id_and_reuses_chunk_reply():
    replies = [
        Reply(Status.OK, True, 2, 0, 5, b"wrong"),
        Reply(Status.OK, True, 1, 1, 5, b"ABCDE"),
    ]
    store = Store({7: replies}, (Piece(7, 1, 2, 0), Piece(7, 3, 2, 2)))
    output = bytearray(b"????tail")
    ChunkReader(store).read_bytes(1, 4, output)
    assert output == b"BCDEtail"
    assert store.calls == [7]
    assert store.plans == [(1, 4)]


def test_quorum_selects_latest_eligible_generation_independent_of_reply_order():
    replies = quorum(b"older", 4) + quorum(b"ABCDE", 5, 3) + quorum(b"newer", 6, 6)
    random = Random(42)
    for _ in range(20):
        random.shuffle(replies)
        store = Store({0: replies})
        output = bytearray(b"???")
        ChunkReader(store, ReadPolicy.QUORUM).read_bytes(0, 3, output)
        assert output == b"BCD"


@pytest.mark.parametrize("policy", list(ReadPolicy))
@pytest.mark.parametrize(
    "change",
    [
        {"status": Status.TIMEOUT},
        {"status": Status.MISSING},
        {"checksum_ok": False},
        {"generation": 6},
        {"data": b"AB"},
    ],
)
def test_ineligible_replies_are_excluded(policy, change):
    replies = quorum()
    invalid = [
        replace(reply, replica_id=reply.replica_id - 10, **change) for reply in replies
    ]
    output = bytearray(b"???")
    ChunkReader(Store({0: invalid + replies}), policy).read_bytes(0, 3, output)
    assert output == b"BCD"


@pytest.mark.parametrize(
    "replies",
    [
        [],
        quorum()[:2],
        [replace(reply, region_id=0) for reply in quorum()],
        [quorum()[0]] * 3,
        quorum(b"ABCxx")[:2] + quorum(b"ABCyy", start_id=2)[:1],
    ],
)
def test_no_quorum_leaves_output_unchanged(replies):
    output = bytearray(b"original")
    store = Store({0: replies}, (Piece(0, 0, 3, 0),))
    with pytest.raises(ReadFailure):
        ChunkReader(store, ReadPolicy.QUORUM).read_bytes(0, 3, output)
    assert output == b"original"


def test_repeated_reply_does_not_invalidate_a_real_quorum():
    replies = quorum()
    output = bytearray(b"???")
    ChunkReader(Store({0: replies + [replies[0]]}), ReadPolicy.QUORUM).read_bytes(
        0, 3, output
    )
    assert output == b"BCD"


@pytest.mark.parametrize(
    "extra",
    [quorum(b"other", start_id=3), [replace(quorum()[0], region_id=99)]],
)
def test_conflicting_same_generation_or_replica_fails_closed(extra):
    output = bytearray(b"???")
    with pytest.raises(ReadFailure, match="conflicting"):
        ChunkReader(Store({0: quorum() + extra}), ReadPolicy.QUORUM).read_bytes(
            0, 3, output
        )
    assert output == b"???"


def test_later_chunk_failure_cannot_partially_commit_earlier_piece():
    pieces = (Piece(0, 0, 2, 0), Piece(1, 0, 2, 2))
    store = Store({0: quorum(), 1: []}, pieces)
    output = bytearray(b"original")
    with pytest.raises(ReadFailure):
        ChunkReader(store, ReadPolicy.QUORUM).read_bytes(0, 4, output)
    assert output == b"original"
    assert store.calls == [0, 1]


def test_out_of_order_pieces_cover_output_and_reuse_replica_fetches():
    pieces = (Piece(0, 3, 2, 2), Piece(1, 0, 2, 4), Piece(0, 1, 2, 0))
    store = Store({0: quorum(), 1: quorum(b"FG")}, pieces)
    output = bytearray(b"??????tail")
    before = {chunk: tuple(replies) for chunk, replies in store.replies.items()}
    ChunkReader(store, ReadPolicy.QUORUM).read_bytes(0, 6, output)
    assert output == b"BCDEFGtail"
    assert Counter(store.calls) == {0: 1, 1: 1}
    assert before == {chunk: tuple(replies) for chunk, replies in store.replies.items()}


@pytest.mark.parametrize("phase", ["plan", "read"])
def test_store_errors_propagate_without_mutating_output(phase):
    failure = OSError("store unavailable")

    class BrokenStore(Store):
        def plan(self, offset, num_bytes):
            if phase == "plan":
                raise failure
            return super().plan(offset, num_bytes)

        def read_replicas(self, chunk):
            raise failure

    output = bytearray(b"???")
    with pytest.raises(OSError) as caught:
        ChunkReader(BrokenStore({}), ReadPolicy.QUORUM).read_bytes(0, 3, output)
    assert caught.value is failure
    assert output == b"???"


@pytest.mark.parametrize(
    "pieces",
    [
        (),
        (Piece(0, 0, 2, 0),),
        (Piece(0, 0, 4, 0),),
        (Piece(0, -1, 3, 0),),
        (Piece(0, 0, 3, -1),),
        (Piece(0, 0, 2, 0), Piece(1, 0, 1, 1)),
        (Piece(0, 0, 1, 0), Piece(1, 0, 1, 2)),
    ],
)
def test_invalid_plan_cannot_resize_or_partially_overwrite_output(pieces):
    store = Store({}, pieces)
    output = bytearray(b"???tail")
    with pytest.raises(ReadFailure):
        ChunkReader(store).read_bytes(0, 3, output)
    assert output == b"???tail"
    assert store.calls == []


def test_zero_length_read_needs_neither_buffer_nor_store_calls():
    store = Store({})
    ChunkReader(store).read_bytes(999, 0, None)
    assert store.plans == store.calls == []


@pytest.mark.parametrize(
    "length, output", [(-1, bytearray()), (1, None), (3, bytearray(2))]
)
def test_invalid_buffer_request_is_rejected_before_planning(length, output):
    store = Store({})
    with pytest.raises(ValueError):
        ChunkReader(store).read_bytes(0, length, output)
    assert store.plans == []
