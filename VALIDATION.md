# Validation

Tested locally on macOS with CPython 3.13.7 and the versions in
`requirements.txt`.

```sh
.venv/bin/python run_samples.py all
```

- `bounded_bucket`: 11 passed.
- `resize`: 15 passed.
- `dropna`: 18 passed.
- `groupby_nth`: 47 passed.
- `match_to_schema`: 35 passed.

Total: **126 passed** across the sample runs. The latest `match_to_schema` update
was verified with `.venv/bin/python run_samples.py match_to_schema` (35 passed); the other
sample results above remain from their most recent runs. Each sample was applied
to a separate temporary copy of its pinned installed package, with an assertion that imports came from that
patched copy. No installed package or original practice checkout was modified.

All five complete patches also passed `git apply --check --whitespace=error`
against the corresponding pinned upstream source files, including documentation
hunks where present.

The runner and test files passed Ruff lint and formatting checks (Ruff 0.14.0).
These are focused feature/regression checks, not the full upstream test matrices
or performance benchmarks. The two Polars patches were tested separately.
