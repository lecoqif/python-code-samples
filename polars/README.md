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

Position values use Polars' expression coercion, including NumPy integer scalars.
Native grouping schema resolution handles missing and duplicate keys. Explicit
checks are limited to valid `dropna` values and the supported grouping context.

Forty-seven checks cover positions, native integer coercion and key errors,
nulls/NaNs, nested payloads, group reuse, typed empty frames, unsupported grouping
contexts, streaming collection, scans, and lazy plan construction without row
execution.

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

The lazy method uses Polars' existing selector parser to resolve names and dtypes,
builds one validity expression per selected column, sums valid values horizontally,
and filters by the required count. This supports `how="any"`, `how="all"`, and explicit `thresh`, while
retaining all original columns and row order. An empty subset has defined
zero-valid-value semantics.

Eighteen checks cover null/NaN behavior, subsets, thresholds, nested values,
empty inputs, multiple chunks, native selectors, argument conflicts, scans,
streaming execution, and construction of a lazy plan without executing rows.

`subset` follows the same selector conventions as `drop_nulls` and `drop_nans`,
including collections of names, duplicate-name deduplication, and selectors.
The only explicit argument checks are valid `how` values and mutual exclusion
of `how` and `thresh`; column parsing and errors use the existing Polars machinery.
The implementation resolves the schema during planning. Large-schema planning
cost is a useful target for future measurement.
