from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    MISSING = "missing"


class ReadPolicy(str, Enum):
    PRIMARY = "primary"
    QUORUM = "quorum"


@dataclass(frozen=True, slots=True)
class Reply:
    status: Status
    checksum_ok: bool
    replica_id: int
    region_id: int
    generation: int
    data: bytes


@dataclass(frozen=True, slots=True)
class Piece:
    chunk: int
    begin_in_chunk: int
    length: int
    output_offset: int


@dataclass(frozen=True, slots=True)
class ReadPlan:
    snapshot_generation: int
    pieces: tuple[Piece, ...]
