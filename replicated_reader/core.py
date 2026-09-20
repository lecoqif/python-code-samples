"""Resolve every planned piece before modifying the caller's output buffer."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol

from .model import Piece, ReadPlan, ReadPolicy, Reply, Status

QUORUM_REPLICAS = 3
QUORUM_REGIONS = 2


class ReplicaStore(Protocol):
    def plan(self, offset: int, num_bytes: int) -> ReadPlan: ...

    def read_replicas(self, chunk: int) -> Sequence[Reply]: ...


class ReadFailure(RuntimeError):
    """The read cannot be resolved without violating its snapshot policy."""


class ChunkReader:
    """Read into an existing buffer; failures leave its bytes unchanged.

    A store supplies a plan covering the requested output exactly once and a
    collection of replica replies for each chunk. Each distinct chunk is fetched
    once per call. This synchronous reader models selection and commit semantics;
    it does not implement replication, network retries, or a consensus protocol.
    """

    def __init__(
        self, store: ReplicaStore, policy: ReadPolicy = ReadPolicy.PRIMARY
    ) -> None:
        if not isinstance(policy, ReadPolicy):
            raise ValueError("unknown read policy")
        self._store = store
        self._policy = policy

    @staticmethod
    def _quorum_data(replies: Sequence[Reply]) -> bytes:
        unique: dict[int, Reply] = {}
        for reply in replies:
            previous = unique.get(reply.replica_id)
            if previous is not None and previous != reply:
                raise ReadFailure("conflicting replies from one replica")
            unique[reply.replica_id] = reply

        agreements: dict[tuple[int, bytes], list[Reply]] = defaultdict(list)
        for reply in unique.values():
            agreements[(reply.generation, reply.data)].append(reply)
        versions = [
            version
            for version, voters in agreements.items()
            if len(voters) >= QUORUM_REPLICAS
            and len({reply.region_id for reply in voters}) >= QUORUM_REGIONS
        ]
        if not versions:
            raise ReadFailure("no cross-region quorum")
        generation = max(version[0] for version in versions)
        newest = [data for version, data in versions if version == generation]
        if len(newest) != 1:
            raise ReadFailure("conflicting quorums at the same generation")
        return newest[0]

    def _resolve(self, replies: Sequence[Reply], plan: ReadPlan, piece: Piece) -> bytes:
        end = piece.begin_in_chunk + piece.length
        eligible = [
            reply
            for reply in replies
            if reply.status is Status.OK
            and reply.checksum_ok
            and reply.generation <= plan.snapshot_generation
            and end <= len(reply.data)
        ]
        if not eligible:
            raise ReadFailure(f"no eligible replica for chunk {piece.chunk}")
        if self._policy is ReadPolicy.PRIMARY:
            data = min(eligible, key=lambda reply: reply.replica_id).data
        else:
            data = self._quorum_data(eligible)
        return data[piece.begin_in_chunk : end]

    def read_bytes(self, offset: int, num_bytes: int, output: bytearray | None) -> None:
        if num_bytes < 0:
            raise ValueError("num_bytes must be non-negative")
        if num_bytes == 0:
            return
        if output is None or len(output) < num_bytes:
            raise ValueError("output is too small")

        plan = self._store.plan(offset, num_bytes)
        position = 0
        for piece in sorted(plan.pieces, key=lambda piece: piece.output_offset):
            if (
                piece.output_offset != position
                or piece.length <= 0
                or piece.begin_in_chunk < 0
            ):
                raise ReadFailure("plan must cover the output exactly once")
            position += piece.length
        if position != num_bytes:
            raise ReadFailure("plan length differs from the requested length")

        cached: dict[int, Sequence[Reply]] = {}
        resolved: list[tuple[Piece, bytes]] = []
        for piece in plan.pieces:
            if piece.chunk not in cached:
                cached[piece.chunk] = tuple(self._store.read_replicas(piece.chunk))
            resolved.append((piece, self._resolve(cached[piece.chunk], plan, piece)))

        for piece, data in resolved:
            start = piece.output_offset
            output[start : start + piece.length] = data
