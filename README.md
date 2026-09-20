# Python code samples

Five extensions to established Python libraries and standalone samples covering
concurrency, tokenization, and replicated reads, with design notes and executable tests.
Each library patch targets a pinned upstream revision, preserving its surrounding
architecture.

Related project: [Grounded tool agent](https://github.com/lecoqif/grounded-tool-agent),
a reporting agent with typed tools, evidence validation, and an offline demo.

## Samples

- **[Longest-match vocabulary tokenizer](tokenization/README.md)** — compare
  reference and trie implementations, handle unknown input, and verify both
  against generated cases. Includes a reproducible benchmark.
  [Implementation](tokenization/tokenizer.py) · [Tests](tokenization/test_tokenizer.py)
- **[Replicated snapshot reader](replicated_reader/README.md)** — select a
  cross-region quorum under a generation bound and commit output atomically.
  [Implementation](replicated_reader/core.py) · [Tests](replicated_reader/test_reader.py)
- **[Bounded parallel maps](concurrency/bounded_map.md)** — preserve input order
  with bounded thread or async submissions, propagate failures, and wait for
  worker cleanup on error or async cancellation.
  [Implementation](concurrency/bounded_map.py) ·
  [Tests](concurrency/test_bounded_map.py)
- **[Concurrent graph crawler](concurrency/README.md)** — coordinate bounded
  parallel fetches, deduplicate discoveries, propagate failures, and clean up
  workers. [Implementation](concurrency/graph_crawler.py) ·
  [Tests](concurrency/test_graph_crawler.py)
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
environment. Other names: `match_to_schema`, `resize`, `dropna`, `bounded_bucket`,
`graph_crawler`, `bounded_map`, `tokenizer`, `replicated_reader`.

The runner copies the installed package into a temporary directory under
`.runs/`, checks and applies that sample's runtime patch, verifies the import
location, and runs its tests in a subprocess. It leaves installed packages
unchanged and removes the temporary copy afterward. The two Polars samples are
tested independently. Documentation hunks are included for source integration
and skipped when applying patches to wheels. The standalone samples
are tested directly, without applying a patch.

The feature suite currently passes **215 tests**. See
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

The library APIs and implementation context come from pandas, Polars,
cachetools, and more-itertools. The five patches target their source trees.
Each upstream project directory includes its license; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Original repository material is
MIT-licensed, with upstream portions retaining their original license terms.
