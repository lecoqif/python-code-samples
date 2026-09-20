# DataFrame schema matching

[Patch](match_to_schema.patch) · [Tests](test_match_to_schema.py) ·
[Upstream baseline](https://github.com/pandas-dev/pandas/tree/9c8bc3e55188c8aff37207a74f1dd144980b8874)

Adds `DataFrame.match_to_schema` to pandas 2.3.3. It returns independent data in
schema column order, with explicit policies for missing/extra columns and casts.

```python
import pandas as pd

frame = pd.DataFrame({"quantity": [2, 3], "obsolete": [8, 9]}, index=[20, 10])
result = frame.match_to_schema(
    {"symbol": "string", "quantity": "Int64"},
    missing_columns="insert",
    extra_columns="drop",
    cast=True,
)
assert result.columns.tolist() == ["symbol", "quantity"]
assert result.index.tolist() == [20, 10]
```

## Design

Validate labels, policies, and normalized target dtypes before constructing the
result. Existing columns are copied and optionally converted using `astype`;
missing columns are built with their requested dtype and original index. A
single DataFrame constructor assembles the columns, avoiding repeated insertion
and wide-frame fragmentation.

The result preserves duplicate index labels, named MultiIndexes, row order,
and `columns.name`. Scalar writes to either frame are isolated with pandas
Copy-on-Write enabled or disabled. A conversion failure leaves the input intact.

## Supported scope

Labels must be unique strings. Target dtypes include native NumPy integer,
bool, float32/64, pandas nullable numeric and boolean types, and Python-backed
nullable strings. NumPy integer/bool columns cannot be inserted as all-missing,
including in empty frames. An empty schema can retain all rows with zero columns.

Twenty-five tests cover normal conversion, strict matching, name policies,
MultiIndex metadata, empty inputs, invalid dtypes, mutation isolation, failure
atomicity, and wide frames with performance warnings promoted to errors.

Casting follows normal pandas semantics and can lose information. Nested
mutable objects inside cells are not recursively copied. The implementation
allocates a new result; peak-memory benchmarks and optional lossless-cast rules
would be useful follow-up work.
