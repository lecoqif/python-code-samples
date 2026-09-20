# Polars row-selection extensions

Both samples target [Polars 1.44.2 at this revision](https://github.com/pola-rs/polars/tree/1bd8ec12f42d40fcec62badf32ef2177d2377d8d).
They build native lazy expressions, with eager methods delegating to the same
implementation. Each patch is independently applicable to the baseline.

## GroupBy.nth

[Patch](groupby_nth.patch) · [Tests](test_groupby_nth.py)

Select original rows by positions within their group. Negative positions count
from the end; out-of-range positions are ignored; duplicate positions and
positive/negative aliases return each row once. Output follows input row order.

```python
import polars as pl

frame = pl.DataFrame({"value": [10, 20, 30], "key": ["a", "b", "a"]})
result = frame.lazy().group_by("key").nth(-1).collect()
assert result["value"].to_list() == [20, 30]
```

The lazy group stores the original frame and supported key names. Optional
missing-value filtering happens before numbering. A window expression computes
each row's group position and group length; membership predicates select both
positive and negative positions without rearranging rows.

Sixty-four checks cover positions, missing keys, nulls/NaNs, nested payloads,
group reuse, typed empty frames, validation, unsupported grouping contexts,
streaming collection, scans, and lazy plan construction without row execution.

The supported grouping keys are distinct existing column names. Expression
keys, selectors, named keys, generators, temporal groups, and groups with
`having` predicates are rejected by `nth`; existing aggregations retain their
behavior. Streaming-engine correctness is checked, but constant-memory execution
is not guaranteed for group-wide window operations. Broader key support and
large-data memory benchmarks are natural next steps.

## dropna

[Patch](dropna.patch) · [Tests](test_dropna.py)

Filter rows using top-level nulls and floating NaNs as missing values. Infinity
and non-null containers containing nested nulls remain valid.

```python
frame = pl.DataFrame({"x": [1.0, None, float("nan")], "y": [None, 2, None]})
result = frame.lazy().dropna(how="all").collect()
assert result.height == 2
```

The lazy method resolves column names and dtypes, builds one validity expression
per selected column, sums valid values horizontally, and filters by the required
count. This supports `how="any"`, `how="all"`, and explicit `thresh`, while
retaining all original columns and row order. An empty subset has defined
zero-valid-value semantics.

Eighteen checks cover null/NaN behavior, subsets, thresholds, nested values,
empty inputs, multiple chunks, argument validation, scans, streaming execution,
and construction of a lazy plan without executing rows.

`subset` accepts column names and sequences of names. Selector expressions are
outside this sample's contract. It resolves the schema during planning; broader
selector support should reuse Polars' selector expansion rather than introduce
a second parsing system.
