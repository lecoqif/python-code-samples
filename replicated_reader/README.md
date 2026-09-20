# Replicated snapshot reader

[Implementation](core.py) · [Models](model.py) · [Tests](test_reader.py)

A synchronous reader that selects eligible replica data for a store-provided
read plan and fills a caller-owned byte buffer. It resolves every piece before
committing any bytes, so planning, store, and replica-selection failures leave
the output unchanged.

The small `ReplicaStore` protocol supplies a `ReadPlan` and replica replies.
`Piece` records source-chunk and destination-buffer offsets. Immutable models
make the ownership boundary explicit. No network service is required.

```python
from replicated_reader import ChunkReader, ReadPolicy

# store implements plan(offset, num_bytes) and read_replicas(chunk).
output = bytearray(1024)
reader = ChunkReader(store, ReadPolicy.QUORUM)
reader.read_bytes(offset=4096, num_bytes=1024, output=output)
```

## Selection policy

Replies are eligible only if their status is OK, checksum is valid, generation
does not exceed the plan's snapshot bound, and data covers the complete piece.

- `PRIMARY` preserves deterministic selection by choosing the eligible reply
  with the lowest replica ID.
- `QUORUM` requires three distinct replica IDs across at least two regions,
  agreeing on both generation and the **entire chunk data**. Agreement on just
  the requested slice is insufficient. Select the highest qualifying generation.

Repeated identical replies count once. Conflicting eligible replies from one
replica, or different qualifying data at the highest generation, raise
`ReadFailure` rather than selecting an arbitrary value.

Plans must cover the requested output exactly once, without gaps or overlap;
malformed plans are rejected before fetching chunks. Pieces may arrive in any
order. Each distinct chunk is fetched once per read, and the caller's buffer
tail beyond the requested length is preserved. Zero-length reads allow no buffer
and perform no store calls. Other store exceptions propagate unchanged.

This models read selection under an upper generation bound. It does not establish
a globally consistent snapshot, implement consensus, prove a checksum, or manage
network timeouts. The store supplies the plan, generation metadata, and checksum
verdicts. Replica IDs and region assignments must represent real independent
replicas in any larger integration.

Storage includes cached replies for the distinct chunks and resolved bytes for
the requested output. Sorting P plan pieces costs O(P log P); selection scans
the eligible replies per piece, with hashing of full chunk bytes for quorum
grouping. Large reads therefore need proportionate memory to preserve atomic
output updates.

## Verification

```sh
.venv/bin/python run_samples.py replicated_reader
```

Thirty-five tests cover both policies, eligibility, generation ordering,
cross-region agreement, duplicate votes, conflicting quorums, exact chunk-data
agreement, invalid plans, repeated chunks, preserved output tails, and failures
after an earlier piece has resolved. The module uses only the standard library;
tests use pytest and in-memory stores.
