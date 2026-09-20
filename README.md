# Python code samples

Five practice extensions to established Python libraries, with focused patches,
design notes, and executable regression tests. Each patch targets a pinned
upstream revision, preserving the surrounding library architecture.

## Samples

- **[pandas: schema matching](pandas/README.md)** — align a DataFrame to an
  ordered schema, validate dtypes, insert missing columns, and preserve indexes
  and mutation isolation. [Implementation](pandas/match_to_schema.patch) ·
  [Tests](pandas/test_match_to_schema.py)
- **[cachetools: live resizing](cachetools/README.md)** — change cache capacity
  through existing eviction policies, including weighted sizes and expiration.
  [Implementation](cachetools/resize.patch) · [Tests](cachetools/test_resize.py)
- **[Polars: GroupBy.nth](polars/README.md#groupbynth)** — select original rows by
  positive or negative group positions using lazy window expressions.
  [Implementation](polars/groupby_nth.patch) · [Tests](polars/test_groupby_nth.py)
- **[Polars: dropna](polars/README.md#dropna)** — filter top-level nulls and NaNs
  with subset, threshold, and any/all semantics in eager and lazy execution.
  [Implementation](polars/dropna.patch) · [Tests](polars/test_dropna.py)
- **[more-itertools: bounded bucket](more_itertools/README.md)** — add bounded
  buffering and resumable backpressure to interleaved iterator consumers.
  [Implementation](more_itertools/bounded_bucket.patch) ·
  [Tests](more_itertools/test_bounded_bucket.py)

## Run the samples

Requires Git and Python 3.13. From the repository root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_samples.py all
```

Alternatively, with `uv`:

```sh
uv venv --python 3.13
uv pip install -r requirements.txt
uv run --no-project python run_samples.py all
```

Run one sample with `python run_samples.py groupby_nth` in the activated
environment. Other names: `match_to_schema`, `resize`, `dropna`, `bounded_bucket`.

The runner copies the installed package into a temporary directory under
`.runs/`, checks and applies that sample's runtime patch, verifies the import
location, and runs its tests in a subprocess. It leaves installed packages
unchanged and removes the temporary copy afterward. The two Polars samples are
tested independently. Documentation hunks are included for source integration
and skipped when applying patches to wheels.

The feature suite currently passes **126 tests**. See
[validation details](VALIDATION.md) for coverage and limits. Running `pytest`
directly against unpatched wheels will not exercise these extensions.

## Read or apply a patch

Each sample README links its exact upstream revision. To integrate a patch,
check out that revision in a separate clone and run:

```sh
git apply --check /path/to/python-code-samples/polars/groupby_nth.patch
git apply /path/to/python-code-samples/polars/groupby_nth.patch
```

The patches contain only the relevant source changes. Full library histories,
native binaries, and virtual environments are omitted. Revisions, package
versions, paths, and test entry points are recorded in [samples.json](samples.json).

## Attribution

The surrounding APIs and implementation context come from pandas, Polars,
cachetools, and more-itertools. These are practice patches against their source
trees. Each project directory includes its upstream license; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Original repository material is
MIT-licensed, with upstream portions retaining their original license terms.
