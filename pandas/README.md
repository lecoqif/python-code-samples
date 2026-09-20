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

Use pandas' dtype normalization, `Index` operations, `Series` construction, and
`astype` for dtype and label handling. Existing columns are copied and optionally
converted; missing columns use pandas' native missing-value defaults for their
dtype and the original row index. A single DataFrame constructor assembles the
columns, avoiding repeated insertion and wide-frame fragmentation.

The result preserves duplicate index labels, named MultiIndexes, row order,
and `columns.name`. Scalar writes to either frame are isolated with pandas
Copy-on-Write enabled or disabled. A conversion failure leaves the input intact.

## Supported scope

Column labels must be unique and flat; integer and tuple labels follow normal
pandas index handling. MultiIndex columns remain outside this sample's scope.
Target dtypes follow pandas' native support, including object, float16, complex,
datetime, categorical, and nullable dtypes, without a separate allowlist.

Explicit checks protect the missing/extra-column policies, strict dtype matching,
and column-shape requirements. NumPy integer/bool columns cannot be inserted as
all-missing, including in empty frames: pandas would otherwise promote integers
or fill boolean columns with `True`. An empty schema can retain all rows with
zero columns.

Thirty-five tests cover native dtype conversion and missing-value defaults,
strict matching, name policies, flat labels, MultiIndex row metadata, empty
inputs, invalid dtypes, mutation isolation, failure atomicity, and wide frames
with performance warnings promoted to errors.

Casting follows normal pandas semantics and can lose information. Nested
mutable objects inside cells are not recursively copied. The implementation
allocates a new result; peak-memory benchmarks and optional lossless-cast rules
would be useful follow-up work.
