from __future__ import annotations

from typing import Any

import numpy as np
import polars.selectors as cs
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

import polars as pl


@pytest.mark.parametrize("maintain_order", [False, True])
@pytest.mark.parametrize(
    ("positions", "rows"),
    [
        (1, [2, 3]),
        (-1, [3, 4]),
        ((-1, 0, 0, 99), [0, 1, 3, 4]),
        ([2, -1, 0, -3], [0, 1, 3, 4]),
        ([], []),
        ([-(2**63), 2**63 - 1], []),
    ],
)
def test_nth_positions_and_original_rows(
    positions: Any, rows: list[int], maintain_order: bool
) -> None:
    df = pl.DataFrame(
        {"value": [10, None, 30, 40, 50], "key": ["a", "b", "a", "b", "a"]}
    )
    expected = df[rows] if rows else df.head(0)
    assert_frame_equal(
        df.group_by("key", maintain_order=maintain_order).nth(positions), expected
    )
    plan = df.lazy().group_by("key", maintain_order=maintain_order).nth(positions)
    assert_frame_equal(plan.collect(), expected)
    assert_frame_equal(plan.collect(engine="streaming"), expected)


@pytest.mark.parametrize(
    ("dropna", "rows"), [(None, [0, 1, 4]), ("any", [3]), ("all", [0, 1, 5])]
)
def test_nth_missing_values_before_numbering(dropna: Any, rows: list[int]) -> None:
    df = pl.DataFrame(
        {
            "value": [None, float("nan"), 2.0, float("inf"), None, 5.0],
            "key": ["a", "b", "a", "b", None, None],
            "nested": [[None], [None], None, [None], None, [None]],
        }
    )
    assert_frame_equal(df.group_by("key").nth([0], dropna=dropna), df[rows])
    assert_frame_equal(
        df.lazy().group_by("key").nth([0], dropna=dropna).collect(engine="streaming"),
        df[rows],
    )


def test_nth_nested_payloads_are_not_missing() -> None:
    df = pl.DataFrame(
        {
            "list": [[None], None],
            "struct": [{"x": None}, None],
            "key": ["a", "a"],
        }
    )
    assert_frame_equal(df.group_by("key").nth(0, dropna="any"), df.head(1))


def test_nth_missing_key_groups_and_signed_zero() -> None:
    df = pl.DataFrame(
        {
            "key": [float("nan"), None, float("nan"), None, 0.0, -0.0],
            "value": list(range(6)),
        }
    )
    expected = df[[2, 3, 5]]
    assert_frame_equal(df.group_by("key").nth(-1), expected)
    assert_frame_equal(
        df.lazy().group_by("key").nth(-1).collect(engine="streaming"), expected
    )


def test_nth_key_forms_and_reuse() -> None:
    df = pl.DataFrame(
        {"value": [10, 20, 30, 40], "key": ["a", "a", "b", "a"], "side": [1, 2, 1, 1]}
    )
    for frame in (df, df.lazy()):
        for by in (("key", "side"), (["key", "side"],), (("key", "side"),)):
            group = frame.group_by(*by)
            before = group.agg(pl.len())
            last = group.nth(-1)
            first = group.nth(0)
            after = group.agg(pl.len())
            if isinstance(frame, pl.LazyFrame):
                before, last, first, after = (
                    result.collect() for result in (before, last, first, after)
                )
            assert_frame_equal(last, df[[1, 2, 3]])
            assert_frame_equal(first, df[[0, 1, 2]])
            assert_frame_equal(before, after, check_row_order=False)


@pytest.mark.parametrize("dropna", [None, "any", "all"])
def test_nth_typed_empty_and_no_eligible_rows(dropna: Any) -> None:
    df = pl.DataFrame(schema={"value": pl.List(pl.Int64), "key": pl.String})
    assert_frame_equal(df.group_by("key").nth([0, -1], dropna=dropna), df)
    nulls = pl.DataFrame({"value": [None, None], "key": [None, None]})
    expected = nulls.head(1) if dropna is None else nulls.head(0)
    assert_frame_equal(nulls.group_by("key").nth(0, dropna=dropna), expected)


@pytest.mark.parametrize(
    "n",
    [True, False, np.int64(1), 1.5, "1", None, {1}, [True], [np.int64(1)], [0, "1"]],
)
@pytest.mark.parametrize("empty", [False, True])
def test_nth_invalid_positions(n: Any, empty: bool) -> None:
    df = pl.DataFrame({"key": ["a"]})
    if empty:
        df = df.head(0)
    for frame in (df, df.lazy()):
        with pytest.raises(TypeError):
            frame.group_by("key").nth(n)


@pytest.mark.parametrize("n", [2**63, -(2**63) - 1, [2**63], [-(2**63) - 1]])
def test_nth_position_overflow(n: Any) -> None:
    with pytest.raises(ValueError, match="64-bit"):
        pl.LazyFrame(schema={"key": pl.String}).group_by("key").nth(n)


@pytest.mark.parametrize("dropna", [False, 0, "bad", [], {}])
def test_nth_invalid_dropna_even_with_empty_positions(dropna: Any) -> None:
    with pytest.raises(ValueError, match="dropna"):
        pl.LazyFrame(schema={"key": pl.String}).group_by("key").nth([], dropna=dropna)


@pytest.mark.parametrize("keys", [[], ["key", "key"], ["absent"]])
@pytest.mark.parametrize("n", [0, []])
def test_nth_key_validation_on_empty_input(keys: list[str], n: Any) -> None:
    df = pl.DataFrame(schema={"key": pl.String})
    error = ColumnNotFoundError if keys == ["absent"] else ValueError
    for frame in (df, df.lazy()):
        with pytest.raises(error):
            frame.group_by(keys).nth(n)


@pytest.mark.parametrize(
    "context", ["expression", "selector", "named", "generator", "having"]
)
def test_nth_unsupported_context_preserves_aggregations(context: str) -> None:
    lf = pl.LazyFrame({"key": [1, 1, 2], "value": [10, 20, 30]})
    if context == "expression":
        group = lf.group_by((pl.col("key") + 1).alias("group"))
    elif context == "selector":
        group = lf.group_by(cs.by_name("key"))
    elif context == "named":
        group = lf.group_by(group="key")
    elif context == "generator":
        group = lf.group_by(name for name in ["key"])
    else:
        group = lf.group_by("key").having(pl.len() > 1)
    expected = group.agg(pl.col("value").sum()).collect()
    with pytest.raises(NotImplementedError):
        group.nth(0)
    assert_frame_equal(
        group.agg(pl.col("value").sum()).collect(), expected, check_row_order=False
    )


def test_nth_rejects_temporal_groups_without_affecting_aggregation() -> None:
    lf = pl.LazyFrame({"time": [0, 1, 2], "value": [10, 20, 30]})
    for group in (
        lf.rolling("time", period="2i"),
        lf.group_by_dynamic("time", every="2i"),
    ):
        expected = group.agg(pl.col("value").sum()).collect()
        with pytest.raises(NotImplementedError):
            group.nth(0)
        assert_frame_equal(group.agg(pl.col("value").sum()).collect(), expected)


def test_nth_scan_chunks_and_downstream_optimization(tmp_path: Any) -> None:
    df = pl.DataFrame({"value": [10, 20, 30, 40, 50], "key": ["a", "b", "a", "b", "a"]})
    chunked = pl.concat([df.head(2), df.slice(2)], rechunk=False)
    assert chunked.n_chunks() > 1
    assert_frame_equal(chunked.group_by("key").nth(1), df[[2, 3]])
    path = tmp_path / "rows.parquet"
    df.write_parquet(path)
    plan = (
        pl.scan_parquet(path)
        .filter(pl.col("value") >= 20)
        .select("value", "key")
        .group_by("key")
        .nth(1)
        .filter(pl.col("value") >= 40)
        .select("value")
    )
    for engine in ("auto", "streaming"):
        assert_frame_equal(plan.collect(engine=engine), df[[3, 4]].select("value"))


def test_nth_builds_plan_without_executing_rows() -> None:
    def fail_if_executed(batch: pl.DataFrame) -> pl.DataFrame:
        pytest.fail("nth executed rows while constructing a lazy plan")

    lf = pl.LazyFrame({"key": ["a"], "value": [1]}).map_batches(
        fail_if_executed, schema={"key": pl.String, "value": pl.Int64}
    )
    plan = lf.group_by("key").nth(0, dropna="any")
    assert plan.collect_schema() == lf.collect_schema()
