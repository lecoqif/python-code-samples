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
- `graph_crawler`: 13 passed.
- `bounded_map`: 27 passed.

Total: **166 passed** in the complete sample run. Each library patch was applied
to a separate temporary copy of its pinned installed package, with an assertion
that imports came from that patched copy. The standalone concurrency samples were
tested directly, including bounded submissions, result ordering, failure cleanup,
async cancellation, and a subprocess crawler deadlock regression.
No installed package or original source checkout was modified.

All five complete patches also passed `git apply --check --whitespace=error`
against the corresponding pinned upstream source files, including documentation
hunks where present.

The runner and test files passed Ruff lint and formatting checks (Ruff 0.14.0).
These are focused feature/regression checks, not the full upstream test matrices
or performance benchmarks. The two Polars patches were tested separately.
